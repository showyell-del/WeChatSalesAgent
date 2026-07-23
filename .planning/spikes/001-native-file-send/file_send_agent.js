'use strict';

const RESOURCE_SUFFIX = '/Contents/Resources/wechat.dylib';
const OFFSETS = {
  sendFuncAddr: 0x5121478,
  sendFuncHookDelta: 0x10,
  defaultStartTaskFuncAddr: 0x51173d0,
  req2bufEnterAddr: 0x3e5930c,
  req2bufExitAddr: 0x3e5a260,
  blrX8Addr: 0x3e5938c,
  afterSerializerAddr: 0x3e59394,
  messageLoadAddr: 0x3e597b0,
  removeNodeAddr: 0x3e5ac30,
  deleteNodeAddr: 0x3e5ac38,
  afterDeleteNodeAddr: 0x3e5ac4c,
  preCallbackAddr: 0x3e5ac58,
  messageCleanupAddr: 0x3e5acac,
  autoBufferWriteFunc: 0x3e7ff0c,
  buf2RespAddr: 0x3e7eaf0
};

let listeners = [];
let triggerX0 = ptr(0);
let triggerX1Payload = ptr(0);
let capturedPayloadBase = ptr(0);
let capturedPayloadTemplate = null;
let contextReady = false;
let sending = false;
let taskId = 0;
let messageType = '';
let protoHex = '';
let messageSlot = ptr(0);
let messageSlotOriginal = ptr(0);
let messageNode = ptr(0);
let messagePatched = false;
let nodeDeleted = false;
let protoWritten = false;
let ackSeen = false;

let retOneStub = ptr(0);
let retZeroStub = ptr(0);
let fakeVtable = ptr(0);
let payloadAddr = ptr(0);
let protoAddr = ptr(0);
let nativeAutoBufferWrite = null;
let nativeStartTask = null;
let nativeDefaultStartTask = null;
let nativeCalloc = null;
let nativeMmap = null;
let hookProfile = null;
const objects = {};

function findExport(name) {
  try {
    if (typeof Module.findGlobalExportByName === 'function') {
      const found = Module.findGlobalExportByName(name);
      if (found) return found;
    }
  } catch (_) {}
  try {
    if (typeof Module.getGlobalExportByName === 'function') return Module.getGlobalExportByName(name);
  } catch (_) {}
  try {
    if (typeof Module.findExportByName === 'function') return Module.findExportByName(null, name);
  } catch (_) {}
  return ptr(0);
}

function setupNativeAllocator() {
  const callocAddr = findExport('calloc');
  if (callocAddr && !callocAddr.isNull()) nativeCalloc = new NativeFunction(callocAddr, 'pointer', ['ulong', 'ulong']);
  const mmapAddr = findExport('mmap');
  if (mmapAddr && !mmapAddr.isNull()) nativeMmap = new NativeFunction(mmapAddr, 'pointer', ['pointer', 'ulong', 'int', 'int', 'int', 'long']);
}

function persistentAlloc(size) {
  if (nativeCalloc !== null) {
    const address = nativeCalloc(1, size);
    if (address && !address.isNull()) return address;
  }
  return Memory.alloc(size);
}

function persistentCodeAlloc(size) {
  if (nativeMmap !== null) {
    const PROT_READ = 1;
    const PROT_WRITE = 2;
    const PROT_EXEC = 4;
    const MAP_PRIVATE = 0x0002;
    const MAP_ANON = 0x1000;
    const MAP_JIT = 0x0800;
    let address = nativeMmap(ptr(0), size, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANON | MAP_JIT, -1, 0);
    if (!address || address.isNull() || address.toString() === '0xffffffffffffffff') {
      address = nativeMmap(ptr(0), size, PROT_READ | PROT_WRITE | PROT_EXEC, MAP_PRIVATE | MAP_ANON, -1, 0);
    }
    if (address && !address.isNull() && address.toString() !== '0xffffffffffffffff') return address;
  }
  return Memory.alloc(size);
}

function emit(event, fields) {
  send(Object.assign({category: 'native_file', event: event}, fields || {}));
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

function writable(address) {
  if (!address || address.isNull()) return false;
  const range = Process.findRangeByAddress(address);
  return range !== null && range.protection.indexOf('w') !== -1;
}

function hexBytes(value) {
  if (value.length % 2 !== 0) throw new Error('odd hex length');
  const result = [];
  for (let index = 0; index < value.length; index += 2) {
    result.push(parseInt(value.slice(index, index + 2), 16));
  }
  return result;
}

function bytesHex(buffer) {
  return Array.from(new Uint8Array(buffer)).map(function (value) {
    return value.toString(16).padStart(2, '0');
  }).join('');
}

function writeCString(address, value) {
  address.writeUtf8String(value);
}

function createRetOneAndVtable() {
  retOneStub = persistentCodeAlloc(Process.pageSize);
  Memory.patchCode(retOneStub, 8, function (code) {
    code.writeByteArray([0x20, 0x00, 0x80, 0x52, 0xc0, 0x03, 0x5f, 0xd6]);
  });
  retZeroStub = persistentCodeAlloc(Process.pageSize);
  Memory.patchCode(retZeroStub, 8, function (code) {
    code.writeByteArray([0x00, 0x00, 0x80, 0x52, 0xc0, 0x03, 0x5f, 0xd6]);
  });
  fakeVtable = persistentAlloc(512);
  for (let index = 0; index < 64; index += 1) fakeVtable.add(index * Process.pointerSize).writePointer(retOneStub);
  fakeVtable.add(0x00).writePointer(retZeroStub);
  fakeVtable.add(0x08).writePointer(retZeroStub);
}

function createObject(cgi, code, messageCode, extended) {
  const cgiAddr = persistentAlloc(128);
  const messageObject = persistentAlloc(256);
  writeCString(cgiAddr, cgi);
  messageObject.writeByteArray(new Array(256).fill(0));
  messageObject.add(0x00).writePointer(fakeVtable);
  messageObject.add(0x0c).writeU32(messageCode || 0x6e);
  messageObject.add(0x10).writeU64(3);
  messageObject.add(0x18).writePointer(cgiAddr);
  messageObject.add(0x20).writeU64(code);
  if (extended) {
    messageObject.add(0x28).writeU64(uint64('0x8000000000000030'));
    messageObject.add(0x30).writeU64(uint64('0x0000000001010100'));
  }
  return {cgiAddr: cgiAddr, messageObject: messageObject};
}

function clearMessagePatch(reason) {
  if (!messagePatched || messageSlot.isNull() || nodeDeleted) return;
  try {
    if (writable(messageSlot)) {
      messageSlot.writePointer(messageSlotOriginal);
      emit('message_patch_cleared', {reason: reason, address: messageSlot.toString(), original: messageSlotOriginal.toString()});
    }
  } finally {
    messageSlot = ptr(0);
    messageSlotOriginal = ptr(0);
    messageNode = ptr(0);
    messagePatched = false;
  }
}

function finishFailure(reason) {
  clearMessagePatch(reason);
  emit('failed', {reason: reason, task_id: taskId, message_type: messageType, proto_written: protoWritten, ack_seen: ackSeen});
  sending = false;
  taskId = 0;
  messageType = '';
  protoHex = '';
}

function attach(module) {
  const sendFuncAddr = module.base.add(OFFSETS.sendFuncAddr);
  const sendHookAddr = sendFuncAddr.add(OFFSETS.sendFuncHookDelta);
  const defaultStartTask = module.base.add(OFFSETS.defaultStartTaskFuncAddr);
  const reqEnter = module.base.add(OFFSETS.req2bufEnterAddr);
  const reqExit = module.base.add(OFFSETS.req2bufExitAddr);
  const blrX8 = module.base.add(OFFSETS.blrX8Addr);
  const afterSerializer = module.base.add(OFFSETS.afterSerializerAddr);
  const messageLoad = module.base.add(OFFSETS.messageLoadAddr);
  const removeNode = module.base.add(OFFSETS.removeNodeAddr);
  const deleteNode = module.base.add(OFFSETS.deleteNodeAddr);
  const afterDeleteNode = module.base.add(OFFSETS.afterDeleteNodeAddr);
  const preCallback = module.base.add(OFFSETS.preCallbackAddr);
  const messageCleanup = module.base.add(OFFSETS.messageCleanupAddr);
  const autoWrite = module.base.add(OFFSETS.autoBufferWriteFunc);
  const buf2Resp = module.base.add(OFFSETS.buf2RespAddr);
  const cxaThrow = findExport('__cxa_throw');

  const instructions = {
    send: Instruction.parse(sendFuncAddr).toString(),
    send_hook: Instruction.parse(sendHookAddr).toString(),
    default_start_task: Instruction.parse(defaultStartTask).toString(),
    req_enter: Instruction.parse(reqEnter).toString(),
    req_exit: Instruction.parse(reqExit).toString(),
    blr_x8: Instruction.parse(blrX8).toString(),
    after_serializer: Instruction.parse(afterSerializer).toString(),
    message_load: Instruction.parse(messageLoad).toString(),
    remove_node: Instruction.parse(removeNode).toString(),
    delete_node: Instruction.parse(deleteNode).toString(),
    after_delete_node: Instruction.parse(afterDeleteNode).toString(),
    pre_callback: Instruction.parse(preCallback).toString(),
    message_cleanup: Instruction.parse(messageCleanup).toString(),
    auto_write: Instruction.parse(autoWrite).toString(),
    buf2resp: Instruction.parse(buf2Resp).toString()
  };
  hookProfile = {offsets: OFFSETS, instructions: instructions};
  if (instructions.blr_x8.indexOf('add x4, sp, #0x138') === -1) throw new Error('pre-BLR serializer instruction mismatch');
  if (instructions.after_serializer.indexOf('add x8, sp, #0x80') === -1) throw new Error('post-serializer instruction mismatch');
  if (instructions.message_load.indexOf('ldr x8, [x22, #0x28]') === -1) throw new Error('message load instruction mismatch');
  if (instructions.remove_node.indexOf('mov x1, x23') === -1) throw new Error('remove node instruction mismatch');
  if (instructions.delete_node.indexOf('mov x0, x23') === -1) throw new Error('delete node instruction mismatch');
  if (instructions.after_delete_node.indexOf('str x20') === -1) throw new Error('after delete node instruction mismatch');
  if (instructions.pre_callback.indexOf('ldr x0, [x20, #0x98]') === -1) throw new Error('pre callback instruction mismatch');
  if (instructions.message_cleanup.indexOf('cbz x20') === -1) throw new Error('message cleanup instruction mismatch');
  if (instructions.default_start_task.indexOf('sub sp, sp, #0x1d0') === -1) throw new Error('default StartTask wrapper mismatch');
  if (instructions.auto_write.indexOf('stp x22, x21') === -1) throw new Error('AutoBufferWrite entry mismatch');
  if (instructions.req_exit.indexOf('ldp x28, x27') === -1) throw new Error('Req2Buf exit instruction mismatch');

  nativeStartTask = new NativeFunction(sendFuncAddr, 'int64', ['pointer', 'pointer']);
  nativeDefaultStartTask = new NativeFunction(defaultStartTask, 'int64', ['pointer']);
  nativeAutoBufferWrite = new NativeFunction(autoWrite, 'int', ['pointer', 'pointer', 'int']);

  if (cxaThrow && !cxaThrow.isNull()) {
    listeners.push(Interceptor.attach(cxaThrow, {
      onEnter(args) {
        if (!sending) return;
        let typeName = '';
        let typeInfo = '';
        let namePointer = '';
        try {
          typeInfo = args[1].toString();
          const namePtr = args[1].add(Process.pointerSize).readPointer();
          namePointer = namePtr.toString();
          if (readable(namePtr)) typeName = namePtr.readUtf8String() || '';
        } catch (_) {}
        const frames = Thread.backtrace(this.context, Backtracer.ACCURATE)
          .slice(0, 12)
          .map(function (address) { return DebugSymbol.fromAddress(address).toString(); });
        emit('cxa_throw_seen', {task_id: taskId, message_type: messageType, exception: typeName, type_info: typeInfo, name_pointer: namePointer, object: args[0].toString(), frames: frames});
      }
    }));
  }

  listeners.push(Interceptor.attach(sendHookAddr, {
    onEnter() {
      if (sending) {
        let payloadTask = 0;
        try {
          if (readable(this.context.x1)) payloadTask = this.context.x1.readU32();
        } catch (_) {}
        emit('starttask_seen', {
          task_id: taskId,
          x0: this.context.x0.toString(),
          x1: this.context.x1.toString(),
          x1_task: payloadTask,
          x0_readable: readable(this.context.x0),
          x1_writable: writable(this.context.x1)
        });
      }
      if (contextReady) return;
      triggerX0 = this.context.x0;
      triggerX1Payload = this.context.x1;
      if (!readable(triggerX0) || !writable(triggerX1Payload)) return;
      capturedPayloadBase = triggerX1Payload;
      capturedPayloadTemplate = triggerX1Payload.readByteArray(0x1a0);
      contextReady = true;
      emit('context_ready', {x0: triggerX0.toString(), x1: triggerX1Payload.toString(), template_bytes: 0x1a0});
    }
  }));

  listeners.push(Interceptor.attach(reqEnter, {
    onEnter() {
      if (sending) {
        let x1Value = 0;
        try {
          x1Value = this.context.x1.toUInt32();
        } catch (_) {}
        emit('req2buf_seen', {
          expected_task_id: taskId,
          x1: this.context.x1.toString(),
          x1_u32: x1Value,
          x20: this.context.x20.toString(),
          x24: this.context.x24.toString(),
          x25: this.context.x25.toString()
        });
      }
    }
  }));

  listeners.push(Interceptor.attach(messageLoad, {
    onEnter() {
      if (!sending || taskId === 0 || !objects[messageType]) return;
      if (!readable(this.context.x22.add(0x20)) || this.context.x22.add(0x20).readU32() !== taskId) return;
      const selected = objects[messageType];
      selected.messageObject.add(0x08).writeU32(taskId);
      messageNode = this.context.x22;
      messageSlot = messageNode.add(0x28);
      if (!writable(messageSlot)) {
        finishFailure('message_slot_unwritable');
        return;
      }
      messageSlotOriginal = messageSlot.readPointer();
      messageSlot.writePointer(selected.messageObject);
      messagePatched = true;
      emit('message_object_patched', {task_id: taskId, message_type: messageType, node: messageNode.toString(), address: messageSlot.toString(), original: messageSlotOriginal.toString(), replacement: selected.messageObject.toString()});
    }
  }));

  listeners.push(Interceptor.attach(blrX8, {
    onEnter() {
      if (!sending || taskId === 0 || this.context.x20.toUInt32() !== taskId) return;
      const bytes = hexBytes(protoHex);
      protoAddr.writeByteArray(bytes);
      const autoBuffer = this.context.sp.add(0x140);
      nativeAutoBufferWrite(autoBuffer, protoAddr, bytes.length);
      this.context.x8 = retOneStub;
      protoWritten = true;
      emit('protobuf_written', {task_id: taskId, message_type: messageType, length: bytes.length});
    }
  }));

  listeners.push(Interceptor.attach(afterSerializer, {
    onEnter() {
      if (!sending || taskId === 0 || !messagePatched) return;
      emit('serializer_returned', {task_id: taskId, message_type: messageType});
    }
  }));

  [
    ['remove_node', removeNode],
    ['delete_node', deleteNode],
    ['after_delete_node', afterDeleteNode],
    ['pre_callback', preCallback]
  ].forEach(function (entry) {
    listeners.push(Interceptor.attach(entry[1], {
      onEnter() {
        if (!sending || taskId === 0) return;
        emit('req2buf_landmark', {task_id: taskId, message_type: messageType, label: entry[0], x20: this.context.x20.toString(), x23: this.context.x23.toString()});
        if (entry[0] === 'delete_node' && !messageNode.isNull() && this.context.x23.equals(messageNode)) {
          nodeDeleted = true;
          messageSlot = ptr(0);
          messageSlotOriginal = ptr(0);
          messageNode = ptr(0);
          messagePatched = false;
          emit('wechat_node_deleted', {task_id: taskId, message_type: messageType});
        }
      }
    }));
  });

  listeners.push(Interceptor.attach(preCallback, {
    onEnter() {
      if (!sending || taskId === 0 || !objects[messageType]) return;
      if (!this.context.x20.equals(objects[messageType].messageObject)) return;
      this.context.x20 = ptr(0);
      this.context.pc = messageCleanup;
      emit('fake_message_post_callback_skipped', {task_id: taskId, message_type: messageType});
    }
  }));

  listeners.push(Interceptor.attach(messageCleanup, {
    onEnter() {
      if (!sending || taskId === 0 || !objects[messageType]) return;
      let head = '';
      try {
        if (readable(this.context.x20)) head = bytesHex(this.context.x20.readByteArray(64));
      } catch (_) {}
      emit('message_cleanup_seen', {task_id: taskId, message_type: messageType, x20: this.context.x20.toString(), fake_message: objects[messageType].messageObject.toString(), head_hex: head});
      if (!this.context.x20.equals(objects[messageType].messageObject)) return;
      this.context.x20 = ptr(0);
      emit('fake_message_cleanup_skipped', {task_id: taskId, message_type: messageType});
    }
  }));

  listeners.push(Interceptor.attach(reqExit, {
    onEnter() {
      if (!sending || taskId === 0 || this.context.x25.toUInt32() !== taskId) return;
      emit('req2buf_exit', {task_id: taskId, message_type: messageType});
    }
  }));

  listeners.push(Interceptor.attach(buf2Resp, {
    onEnter() {
      if (!sending || taskId === 0) return;
      let responseTaskId;
      let length;
      try {
        responseTaskId = this.context.sp.add(0x140).readS32();
        length = this.context.x0.toInt32();
      } catch (error) {
        return;
      }
      if (responseTaskId !== taskId) return;
      if (length < 2 || length > 4 * 1024 * 1024 || !readable(this.context.x20)) {
        finishFailure('invalid_buf2resp');
        return;
      }
      const response = this.context.x20.readByteArray(length);
      ackSeen = true;
      emit('buf2resp', {task_id: taskId, message_type: messageType, length: length, data_hex: bytesHex(response)});
      clearMessagePatch('buf2resp');
      const finishedTask = taskId;
      const finishedType = messageType;
      sending = false;
      taskId = 0;
      messageType = '';
      protoHex = '';
      emit('finished', {task_id: finishedTask, message_type: finishedType, proto_written: protoWritten, ack_seen: ackSeen});
    }
  }));
}

function trigger(task, type, messageProtoHex, payloadHex) {
  if (sending) return {ok: false, error: 'already_sending'};
  if (!contextReady || triggerX0.isNull()) return {ok: false, error: 'real_starttask_context_missing'};
  if (!objects[type]) return {ok: false, error: 'unsupported_type'};
  const payload = hexBytes(payloadHex);
  const proto = hexBytes(messageProtoHex);
  if (payload.length !== 0x1a0) return {ok: false, error: 'bad_payload_length'};
  if (proto.length === 0 || proto.length > 1024 * 1024) return {ok: false, error: 'bad_proto_length'};

  taskId = task >>> 0;
  messageType = type;
  protoHex = messageProtoHex;
  protoWritten = false;
  ackSeen = false;
  messageSlot = ptr(0);
  messageSlotOriginal = ptr(0);
  messageNode = ptr(0);
  messagePatched = false;
  nodeDeleted = false;

  const selected = objects[type];
  selected.messageObject.add(0x08).writeU32(taskId);
  payloadAddr.writeByteArray(capturedPayloadTemplate);
  for (let offset = 0; offset <= 0x198; offset += Process.pointerSize) {
    const value = payloadAddr.add(offset).readPointer();
    if (value.compare(capturedPayloadBase) >= 0 && value.compare(capturedPayloadBase.add(0x1a0)) < 0) {
      payloadAddr.add(offset).writePointer(payloadAddr.add(value.sub(capturedPayloadBase).toInt32()));
    }
  }
  payloadAddr.writeU32(taskId);
  [4, 5, 20, 32, 96, 97].forEach(function (offset) { payloadAddr.add(offset).writeU8(payload[offset]); });
  payloadAddr.add(0x18).writePointer(selected.cgiAddr);
  payloadAddr.add(0xb8).writePointer(payloadAddr.add(0xc0));
  payloadAddr.add(0x190).writePointer(payloadAddr.add(0x198));
  sending = true;
  emit('triggering', {task_id: taskId, message_type: type, proto_length: proto.length});
  try {
    const result = nativeStartTask(triggerX0, payloadAddr);
    emit('trigger_returned', {task_id: taskId, message_type: type, return_value: result.toString(), dispatch: 'captured_real_manager'});
    setTimeout(function () {
      if (sending && taskId === (task >>> 0)) finishFailure('response_timeout');
    }, 15000);
    return {ok: true, task_id: taskId};
  } catch (error) {
    finishFailure('native_exception:' + String(error));
    return {ok: false, error: String(error)};
  }
}

const module = moduleForWechat();
setupNativeAllocator();
createRetOneAndVtable();
payloadAddr = persistentAlloc(0x1a0);
protoAddr = persistentAlloc(1024 * 1024);
objects.appattach = createObject('/cgi-bin/micromsg-bin/uploadappattach', 0x25, 0x6e, true);
objects.file = createObject('/cgi-bin/micromsg-bin/sendappmsg', 0x20, 0x6e, true);
objects.text = createObject('/cgi-bin/micromsg-bin/newsendmsg', 0x20, 0x20a);
attach(module);

rpc.exports = {
  status() {
    return {dispatch_ready: nativeDefaultStartTask !== null, context_ready: contextReady, sending: sending, task_id: taskId, message_type: messageType, message_patched: messagePatched, node_deleted: nodeDeleted, proto_written: protoWritten, ack_seen: ackSeen};
  },
  profile() {
    return hookProfile;
  },
  trigger(task, type, messageProtoHex, payloadHex) {
    return trigger(task, type, messageProtoHex, payloadHex);
  },
  forceCleanup() {
    if (sending) finishFailure('host_cleanup');
    listeners.forEach(function (listener) { try { listener.detach(); } catch (_) {} });
    listeners = [];
    return true;
  }
};
