// src/utils/indexedDBUtils.ts

/**
 * 汎用の IndexedDB オープン関数
 * @param dbName データベース名
 * @param version バージョン番号
 * @param upgradeCallback upgrade時のコールバック（オブジェクトストアの作成など）
 */
export function openDB(
    dbName: string,
    version: number,
    upgradeCallback?: (db: IDBDatabase) => void
  ): Promise<IDBDatabase> {
    return new Promise((resolve, reject) => {
      const request = indexedDB.open(dbName, version);
      request.onupgradeneeded = () => {
        const db = request.result;
        if (upgradeCallback) {
          upgradeCallback(db);
        }
      };
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }
  
  /**
   * 汎用のストアからのデータ取得関数
   * @param db オープン済みのデータベース
   * @param storeName オブジェクトストア名
   * @param key キー
   */
  export function getItemFromStore<T>(
    db: IDBDatabase,
    storeName: string,
    key: string
  ): Promise<T | null> {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readonly");
      const store = transaction.objectStore(storeName);
      const request = store.get(key);
      request.onsuccess = () => resolve(request.result || null);
      request.onerror = () => reject(request.error);
    });
  }
  
  /**
   * 汎用のストアへのデータ保存関数
   * @param db オープン済みのデータベース
   * @param storeName オブジェクトストア名
   * @param item 保存するアイテム
   */
  export function setItemToStore(
    db: IDBDatabase,
    storeName: string,
    item: any
  ): Promise<void> {
    return new Promise((resolve, reject) => {
      const transaction = db.transaction(storeName, "readwrite");
      const store = transaction.objectStore(storeName);
      const request = store.put(item);
      request.onsuccess = () => resolve();
      request.onerror = () => reject(request.error);
    });
  }
  