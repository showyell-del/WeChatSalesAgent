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
  autoBufferWriteFunc: 0x3e7ff18,
  buf2RespAddr: 0x3e7eaf0
};

let listeners = [];
let triggerX0 = ptr(0);
let triggerX1Payload = ptr(0);
let contextReady = false;
let sending = false;
let taskId = 0;
let messageType = '';
let protoHex = '';
let insertedAddr = ptr(0);
let insertedOriginal = ptr(0);
let inserted = false;
let protoWritten = false;
let ackSeen = false;

let retOneStub = ptr(0);
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
  fakeVtable = persistentAlloc(512);
  for (let index = 0; index < 64; index += 1) fakeVtable.add(index * Process.pointerSize).writePointer(retOneStub);
}

function createObject(cgi, code) {
  const cgiAddr = persistentAlloc(128);
  const sendObject = persistentAlloc(256);
  const messageObject = persistentAlloc(256);
  writeCString(cgiAddr, cgi);
  sendObject.writeByteArray(new Array(256).fill(0));
  messageObject.writeByteArray(new Array(256).fill(0));
  sendObject.add(0x18).writeU64(1);
  sendObject.add(0x28).writePointer(messageObject);
  messageObject.add(0x00).writePointer(fakeVtable);
  messageObject.add(0x0c).writeU32(0x6e);
  messageObject.add(0x10).writeU64(3);
  messageObject.add(0x18).writePointer(cgiAddr);
  messageObject.add(0x20).writeU64(code);
  messageObject.add(0x28).writeU64(uint64('0x8000000000000030'));
  messageObject.add(0x30).writeU64(uint64('0x0000000001010100'));
  return {cgiAddr: cgiAddr, sendObject: sendObject, messageObject: messageObject};
}

function clearInserted(reason) {
  if (!inserted || insertedAddr.isNull()) return;
  try {
    insertedAddr.writePointer(insertedOriginal);
    emit('insert_cleared', {reason: reason, mode: 'restore_original_message', address: insertedAddr.toString()});
  } finally {
    insertedAddr = ptr(0);
    insertedOriginal = ptr(0);
    inserted = false;
  }
}

function finishFailure(reason) {
  clearInserted(reason);
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
  const autoWrite = module.base.add(OFFSETS.autoBufferWriteFunc);
  const buf2Resp = module.base.add(OFFSETS.buf2RespAddr);

  const instructions = {
    send: Instruction.parse(sendFuncAddr).toString(),
    send_hook: Instruction.parse(sendHookAddr).toString(),
    default_start_task: Instruction.parse(defaultStartTask).toString(),
    req_enter: Instruction.parse(reqEnter).toString(),
    req_exit: Instruction.parse(reqExit).toString(),
    blr_x8: Instruction.parse(blrX8).toString(),
    after_serializer: Instruction.parse(afterSerializer).toString(),
    auto_write: Instruction.parse(autoWrite).toString(),
    buf2resp: Instruction.parse(buf2Resp).toString()
  };
  hookProfile = {offsets: OFFSETS, instructions: instructions};
  if (instructions.blr_x8.indexOf('add x4, sp, #0x138') === -1) throw new Error('pre-BLR serializer instruction mismatch');
  if (instructions.after_serializer.indexOf('add x8, sp, #0x80') === -1) throw new Error('post-serializer instruction mismatch');
  if (instructions.default_start_task.indexOf('sub sp, sp, #0x1d0') === -1) throw new Error('default StartTask wrapper mismatch');
  if (instructions.req_exit.indexOf('ldp x28, x27') === -1) throw new Error('Req2Buf exit instruction mismatch');

  nativeStartTask = new NativeFunction(sendFuncAddr, 'int64', ['pointer', 'pointer']);
  nativeDefaultStartTask = new NativeFunction(defaultStartTask, 'int64', ['pointer']);
  nativeAutoBufferWrite = new NativeFunction(autoWrite, 'int', ['pointer', 'pointer', 'int']);

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
      contextReady = true;
      emit('context_ready', {x0: triggerX0.toString(), x1: triggerX1Payload.toString()});
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
      if (!sending || taskId === 0 || !this.context.x1.equals(ptr(taskId))) return;
      const selected = objects[messageType];
      const requestSlot = this.context.x19.add(0x60);
      if (!readable(requestSlot)) {
        finishFailure('req2buf_request_slot_unreadable');
        return;
      }
      selected.sendObject.add(0x20).writeU32(taskId);
      selected.messageObject.add(0x08).writeU32(taskId);
      insertedAddr = requestSlot;
      insertedOriginal = insertedAddr.readPointer();
      insertedAddr.writePointer(selected.sendObject);
      inserted = true;
      emit('message_object_swapped', {task_id: taskId, message_type: messageType, mode: 'x19_request_slot', address: insertedAddr.toString(), original: insertedOriginal.toString()});
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
      if (!sending || taskId === 0 || !inserted) return;
      emit('serializer_returned', {task_id: taskId, message_type: messageType});
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
      clearInserted('buf2resp');
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
  inserted = false;

  const selected = objects[type];
  selected.messageObject.add(0x08).writeU32(taskId);
  selected.sendObject.add(0x20).writeU32(taskId);
  payloadAddr.writeByteArray(payload);
  payloadAddr.add(0x18).writePointer(selected.cgiAddr);
  payloadAddr.add(0xb8).writePointer(payloadAddr.add(0xc0));
  payloadAddr.add(0x190).writePointer(payloadAddr.add(0x198));
  sending = true;
  emit('triggering', {task_id: taskId, message_type: type, proto_length: proto.length});
  try {
    const result = nativeDefaultStartTask(payloadAddr);
    emit('trigger_returned', {task_id: taskId, message_type: type, return_value: result.toString(), dispatch: 'default_manager_wrapper'});
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
objects.appattach = createObject('/cgi-bin/micromsg-bin/uploadappattach', 0x25);
objects.file = createObject('/cgi-bin/micromsg-bin/sendappmsg', 0x20);
attach(module);

rpc.exports = {
  status() {
    return {dispatch_ready: nativeDefaultStartTask !== null, context_ready: contextReady, sending: sending, task_id: taskId, message_type: messageType, inserted: inserted, proto_written: protoWritten, ack_seen: ackSeen};
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
