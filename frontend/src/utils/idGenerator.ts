// frontend/src/utils/idGenerator.ts
const generateId = (): string => {
  const randomString = Math.random().toString(36).substring(2, 14); // 36進数でランダムな12文字を生成
  return "F" + randomString; // 先頭に "F" を付加
};

export default generateId;
