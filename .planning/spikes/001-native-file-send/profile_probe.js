'use strict';

const MODULE_PATH = '/Applications/WeChat.app/Contents/Resources/wechat.dylib';

const PROBES = [
  {name: 'req2bufEnterAddr', pattern: '09 0F 46 F8 C9 01 00 B4 E8 03 18 AA 2A 21 40 B9', adjust: 0},
  {name: 'sendFuncAddr', pattern: 'E0 03 00 91 21 00 80 52 E5 03 03 AA 46 8A 80 52', adjust: -0x44},
  {name: 'buf2RespAddr', pattern: 'E8 DF C1 39 28 E6 FF 36 E0 33 40 F9 E8 3B 40 F9', adjust: -0x14},
  {name: 'uploadImageAddr', pattern: '08 01 40 F9 A8 83 1A F8 28 9C 40 B9 1F 0D 00 71', adjust: -0x30},
  {name: 'cndOnCompleteAddr', pattern: '68 42 00 91 29 00 80 52 08 01 29 F8 88 12 40 B9', adjust: -0xcc},
  {name: 'uploadGetCallbackWrapperAddr', pattern: '08 09 40 F9 E1 03 15 AA E2 03 14 AA E3 03 13 AA 00 01 3F D6 F3 07 40 F9 B3 00 00 B4', adjust: 0}
];

function emit(event, fields) {
  send(Object.assign({category: 'profile', event: event}, fields || {}));
}

function bytesAt(address, count) {
  return Array.from(new Uint8Array(address.readByteArray(count))).map(function (value) {
    return value.toString(16).padStart(2, '0');
  }).join('');
}

function scanOne(module, probe) {
  return new Promise(function (resolve, reject) {
    const matches = [];
    Memory.scan(module.base, module.size, probe.pattern, {
      onMatch(address) {
        const candidate = address.add(probe.adjust);
        matches.push({
          match_offset: address.sub(module.base).toString(),
          candidate_offset: candidate.sub(module.base).toString(),
          candidate_bytes: bytesAt(candidate, 32)
        });
      },
      onError(reason) {
        reject(new Error(probe.name + ': ' + reason));
      },
      onComplete() {
        emit('scan_complete', {name: probe.name, matches: matches});
        resolve({name: probe.name, matches: matches});
      }
    });
  });
}

rpc.exports = {
  async inspect() {
    const modules = Process.enumerateModules().filter(function (item) {
      return item.path === MODULE_PATH;
    });
    if (modules.length !== 1) {
      throw new Error('expected exactly one wechat.dylib, got ' + modules.length);
    }
    const module = modules[0];
    emit('module', {path: module.path, base: module.base.toString(), size: module.size});
    const results = [];
    for (const probe of PROBES) {
      results.push(await scanOne(module, probe));
    }
    return {module: {path: module.path, size: module.size}, probes: results};
  }
};
