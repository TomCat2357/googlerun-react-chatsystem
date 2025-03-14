import { v4 as uuidv4 } from 'uuid';

// フロントエンド用のリクエストID生成関数
export const generateRequestId = (): string => {
  return `F${uuidv4().replace(/-/g, '').substring(0, 12)}`;
};
