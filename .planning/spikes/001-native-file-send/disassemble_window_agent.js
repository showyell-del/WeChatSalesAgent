'use strict';

const RESOURCE_SUFFIX = '/Contents/Resources/wechat.dylib';

function moduleForWechat() {
  const matches = Process.enumerateModules().filter(function (module) {
    return module.path.endsWith(RESOURCE_SUFFIX);
  });
  if (matches.length !== 1) throw new Error('expected one wechat.dylib, got ' + matches.length);
  return matches[0];
}

function dump(module, start, count) {
  const result = [];
  let cursor = module.base.add(start);
  for (let index = 0; index < count; index += 1) {
    const instruction = Instruction.parse(cursor);
    result.push({offset: cursor.sub(module.base).toString(), address: cursor.toString(), text: instruction.toString()});
    cursor = instruction.next;
  }
  return result;
}

const module = moduleForWechat();

rpc.exports = {
  dump(start, count) {
    return dump(module, start, count);
  }
};
