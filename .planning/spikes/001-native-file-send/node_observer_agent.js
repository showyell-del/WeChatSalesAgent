'use strict';

const RESOURCE_SUFFIX = '/Contents/Resources/wechat.dylib';
const OFFSETS = {
  req2bufEnterAddr: 0x3e5930c,
  removeNodeAddr: 0x3e5ac30,
  deleteNodeAddr: 0x3e5ac38,
  afterDeleteNodeAddr: 0x3e5ac4c,
  preCallbackAddr: 0x3e5ac58
};

let listeners = [];
let emitted = 0;
const MAX_EVENTS = 120;

function emit(event, fields) {
  if (emitted >= MAX_EVENTS) return;
  emitted += 1;
  send(Object.assign({category: 'native_node_observer', event: event}, fields || {}));
}

function moduleForWechat() {
  const matches = Process.enumerateModules().filter(function (module) {
    return module.path.endsWith(RESOURCE_SUFFIX);
  });
  if (matches.length !== 1) throw new Error('expected one wechat.dylib, got ' + matches.length);
  return matches[0];
}

function readable(address) {
  if (!address || address.isNull()) return false;
  const range = Process.findRangeByAddress(address);
  return range !== null && range.protection.indexOf('r') !== -1;
}

function bytesHex(buffer) {
  return Array.from(new Uint8Array(buffer)).map(function (value) {
    return value.toString(16).padStart(2, '0');
  }).join('');
}

function readHead(address, size) {
  try {
    if (!readable(address)) return '';
    return bytesHex(address.readByteArray(size));
  } catch (_) {
    return '';
  }
}

function readPointer(address, offset) {
  try {
    if (!readable(address.add(offset))) return '0x0';
    return address.add(offset).readPointer().toString();
  } catch (_) {
    return '0x0';
  }
}

function readU32(address, offset) {
  try {
    if (!readable(address.add(offset))) return 0;
    return address.add(offset).readU32();
  } catch (_) {
    return 0;
  }
}

function readU8(address, offset) {
  try {
    if (!readable(address.add(offset))) return 0;
    return address.add(offset).readU8();
  } catch (_) {
    return 0;
  }
}

function readUtf8(address, maxLength) {
  try {
    if (!readable(address)) return '';
    return address.readUtf8String(maxLength) || '';
  } catch (_) {
    return '';
  }
}

function describeNode(node) {
  const message = ptr(readPointer(node, 0x28));
  const cgiPointer = ptr(readPointer(message, 0x18));
  return {
    node: node.toString(),
    node_head_hex: readHead(node, 0x40),
    left: readPointer(node, 0x00),
    right: readPointer(node, 0x08),
    parent: readPointer(node, 0x10),
    color: readU8(node, 0x18),
    task_id: readU32(node, 0x20),
    message: message.toString(),
    message_head_hex: readHead(message, 0x60),
    message_vtable: readPointer(message, 0x00),
    message_task_id: readU32(message, 0x08),
    message_code_0c: readU32(message, 0x0c),
    message_u64_10: readPointer(message, 0x10),
    cgi_pointer: cgiPointer.toString(),
    cgi: readUtf8(cgiPointer, 128)
  };
}

function attach(module) {
  const reqEnter = module.base.add(OFFSETS.req2bufEnterAddr);
  const removeNode = module.base.add(OFFSETS.removeNodeAddr);
  const deleteNode = module.base.add(OFFSETS.deleteNodeAddr);
  const afterDeleteNode = module.base.add(OFFSETS.afterDeleteNodeAddr);
  const preCallback = module.base.add(OFFSETS.preCallbackAddr);
  const instructions = {
    req_enter: Instruction.parse(reqEnter).toString(),
    remove_node: Instruction.parse(removeNode).toString(),
    delete_node: Instruction.parse(deleteNode).toString(),
    after_delete_node: Instruction.parse(afterDeleteNode).toString(),
    pre_callback: Instruction.parse(preCallback).toString()
  };
  if (instructions.req_enter.indexOf('ldr x9, [x24, #0x60]!') === -1) throw new Error('Req2Buf entry mismatch');
  if (instructions.remove_node.indexOf('mov x1, x23') === -1) throw new Error('remove node mismatch');
  if (instructions.delete_node.indexOf('mov x0, x23') === -1) throw new Error('delete node mismatch');
  if (instructions.after_delete_node.indexOf('str x20') === -1) throw new Error('after delete node mismatch');
  if (instructions.pre_callback.indexOf('ldr x0, [x20, #0x98]') === -1) throw new Error('pre callback mismatch');
  emit('hook_profile', {offsets: OFFSETS, instructions: instructions});

  listeners.push(Interceptor.attach(reqEnter, {
    onEnter() {
      const task = this.context.x1.toUInt32();
      if (task === 0) return;
      const slot = this.context.x19.add(0x60);
      let node = ptr(0);
      try {
        if (readable(slot)) node = slot.readPointer();
      } catch (_) {}
      const fields = {
        task_id: task,
        x19: this.context.x19.toString(),
        x20: this.context.x20.toString(),
        x24: this.context.x24.toString(),
        x25: this.context.x25.toString(),
        request_slot: slot.toString(),
        slot_node: node.toString()
      };
      if (!node.isNull() && readable(node)) Object.assign(fields, describeNode(node));
      emit('req2buf_real', fields);
    }
  }));

  [
    ['remove_node_real', removeNode],
    ['delete_node_real', deleteNode],
    ['after_delete_node_real', afterDeleteNode],
    ['pre_callback_real', preCallback]
  ].forEach(function (entry) {
    listeners.push(Interceptor.attach(entry[1], {
      onEnter() {
        const node = this.context.x23;
        const fields = {
          label: entry[0],
          x20: this.context.x20.toString(),
          x23: node.toString()
        };
        if (!node.isNull() && readable(node)) Object.assign(fields, describeNode(node));
        emit(entry[0], fields);
      }
    }));
  });
}

const module = moduleForWechat();
attach(module);

rpc.exports = {
  status() {
    return {emitted: emitted, max_events: MAX_EVENTS};
  },
  stop() {
    listeners.forEach(function (listener) { try { listener.detach(); } catch (_) {} });
    listeners = [];
    return true;
  }
};
