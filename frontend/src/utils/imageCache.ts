// src/utils/imageCache.ts
interface ImageCacheKey {
    type: 'satellite' | 'streetview';
    lat: number;
    lng: number;
    zoom?: number;
    heading?: number;
    pitch?: number;
    fov?: number;
  }
  
  class ImageCache {
    private cache: Map<string, string> = new Map();
  
    private generateKey(params: ImageCacheKey): string {
      const keyObj = { ...params };
      return JSON.stringify(keyObj);
    }
  
    set(params: ImageCacheKey, imageData: string) {
      const key = this.generateKey(params);
      this.cache.set(key, imageData);
    }
  
    get(params: ImageCacheKey): string | undefined {
      const key = this.generateKey(params);
      return this.cache.get(key);
    }
  
    clear() {
      this.cache.clear();
    }
  }
  
  export const imageCache = new ImageCache();