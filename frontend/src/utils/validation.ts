/**
 * validation.ts
 * 統一されたバリデーション関数集
 */

export interface ValidationRule {
  required?: boolean;
  minLength?: number;
  maxLength?: number;
  pattern?: RegExp;
  custom?: (value: any) => string | null;
}

export interface ValidationResult {
  isValid: boolean;
  errors: Record<string, string>;
}

/**
 * Base64データの検証
 */
export const validateBase64 = (data: string): boolean => {
  if (!data) return false;
  
  // Data URL形式の場合
  if (data.startsWith('data:')) {
    const parts = data.split(',');
    if (parts.length !== 2) return false;
    return validateBase64String(parts[1]);
  }
  
  return validateBase64String(data);
};

/**
 * Base64文字列の検証（純粋なBase64文字列）
 */
const validateBase64String = (str: string): boolean => {
  try {
    return btoa(atob(str)) === str;
  } catch {
    return false;
  }
};

/**
 * ファイルサイズの検証
 */
export const validateFileSize = (file: File, maxSize: number): string | null => {
  if (file.size > maxSize) {
    const maxSizeMB = Math.round(maxSize / 1024 / 1024);
    const fileSizeMB = Math.round(file.size / 1024 / 1024 * 100) / 100;
    return `ファイルサイズが上限（${maxSizeMB}MB）を超えています（${fileSizeMB}MB）`;
  }
  return null;
};

/**
 * ファイルタイプの検証
 */
export const validateFileType = (file: File, allowedTypes: string[]): string | null => {
  if (allowedTypes.includes('*/*')) return null;
  
  const isAllowed = allowedTypes.some(type => {
    if (type.endsWith('/*')) {
      const category = type.replace('/*', '');
      return file.type.startsWith(category + '/');
    }
    if (type.startsWith('.')) {
      return file.name.toLowerCase().endsWith(type.toLowerCase());
    }
    return file.type === type;
  });
  
  if (!isAllowed) {
    return `許可されていないファイルタイプです: ${file.type}`;
  }
  
  return null;
};

/**
 * 音声ファイルの再生時間検証
 */
export const validateAudioDuration = (
  duration: number,
  maxSeconds: number
): string | null => {
  if (duration > maxSeconds) {
    const maxMinutes = Math.floor(maxSeconds / 60);
    const maxSecs = maxSeconds % 60;
    const durationMinutes = Math.floor(duration / 60);
    const durationSecs = Math.floor(duration % 60);
    
    return `音声ファイルの再生時間が上限（${maxMinutes}分${maxSecs}秒）を超えています（${durationMinutes}分${durationSecs}秒）`;
  }
  return null;
};

/**
 * 画像の解像度検証
 */
export const validateImageResolution = (
  width: number,
  height: number,
  maxWidth: number,
  maxHeight: number
): string | null => {
  if (width > maxWidth || height > maxHeight) {
    return `画像の解像度が上限（${maxWidth}x${maxHeight}）を超えています（${width}x${height}）`;
  }
  return null;
};

/**
 * メールアドレスの検証
 */
export const validateEmail = (email: string): string | null => {
  if (!email) return 'メールアドレスは必須です';
  
  const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  if (!emailRegex.test(email)) {
    return '有効なメールアドレスを入力してください';
  }
  
  return null;
};

/**
 * パスワードの検証
 */
export const validatePassword = (password: string, minLength = 8): string | null => {
  if (!password) return 'パスワードは必須です';
  
  if (password.length < minLength) {
    return `パスワードは${minLength}文字以上で入力してください`;
  }
  
  // 大文字、小文字、数字、特殊文字のうち3種類以上含む
  const hasUpperCase = /[A-Z]/.test(password);
  const hasLowerCase = /[a-z]/.test(password);
  const hasNumbers = /\d/.test(password);
  const hasSpecialChar = /[!@#$%^&*(),.?":{}|<>]/.test(password);
  
  const criteriaCount = [hasUpperCase, hasLowerCase, hasNumbers, hasSpecialChar]
    .filter(Boolean).length;
  
  if (criteriaCount < 3) {
    return 'パスワードは大文字、小文字、数字、特殊文字のうち3種類以上を含む必要があります';
  }
  
  return null;
};

/**
 * URL形式の検証
 */
export const validateUrl = (url: string): string | null => {
  if (!url) return 'URLは必須です';
  
  try {
    new URL(url);
    return null;
  } catch {
    return '有効なURLを入力してください';
  }
};

/**
 * 必須入力の検証
 */
export const validateRequired = (value: any, fieldName: string): string | null => {
  if (value === null || value === undefined || value === '' || 
      (Array.isArray(value) && value.length === 0)) {
    return `${fieldName}は必須です`;
  }
  return null;
};

/**
 * 文字列長の検証
 */
export const validateStringLength = (
  value: string,
  minLength?: number,
  maxLength?: number,
  fieldName?: string
): string | null => {
  if (minLength !== undefined && value.length < minLength) {
    return `${fieldName || '入力値'}は${minLength}文字以上で入力してください`;
  }
  
  if (maxLength !== undefined && value.length > maxLength) {
    return `${fieldName || '入力値'}は${maxLength}文字以内で入力してください`;
  }
  
  return null;
};

/**
 * 数値の範囲検証
 */
export const validateNumberRange = (
  value: number,
  min?: number,
  max?: number,
  fieldName?: string
): string | null => {
  if (min !== undefined && value < min) {
    return `${fieldName || '数値'}は${min}以上で入力してください`;
  }
  
  if (max !== undefined && value > max) {
    return `${fieldName || '数値'}は${max}以下で入力してください`;
  }
  
  return null;
};

/**
 * 日付の検証
 */
export const validateDate = (date: string | Date, fieldName?: string): string | null => {
  const dateObj = typeof date === 'string' ? new Date(date) : date;
  
  if (isNaN(dateObj.getTime())) {
    return `${fieldName || '日付'}が無効です`;
  }
  
  return null;
};

/**
 * 複数の検証ルールを適用
 */
export const validateField = (
  value: any,
  rules: ValidationRule,
  fieldName?: string
): string | null => {
  // 必須チェック
  if (rules.required) {
    const requiredError = validateRequired(value, fieldName || 'フィールド');
    if (requiredError) return requiredError;
  }
  
  // 値が空の場合、必須でなければOK
  if (!rules.required && (value === null || value === undefined || value === '')) {
    return null;
  }
  
  // 文字列長チェック
  if (typeof value === 'string') {
    const lengthError = validateStringLength(
      value,
      rules.minLength,
      rules.maxLength,
      fieldName
    );
    if (lengthError) return lengthError;
  }
  
  // パターンマッチ
  if (rules.pattern && typeof value === 'string') {
    if (!rules.pattern.test(value)) {
      return `${fieldName || 'フィールド'}の形式が正しくありません`;
    }
  }
  
  // カスタムバリデーション
  if (rules.custom) {
    const customError = rules.custom(value);
    if (customError) return customError;
  }
  
  return null;
};

/**
 * オブジェクト全体の検証
 */
export const validateObject = <T extends Record<string, any>>(
  data: T,
  rules: Record<keyof T, ValidationRule>
): ValidationResult => {
  const errors: Record<string, string> = {};
  
  for (const [fieldName, rule] of Object.entries(rules)) {
    const value = data[fieldName];
    const error = validateField(value, rule as ValidationRule, fieldName);
    
    if (error) {
      errors[fieldName] = error;
    }
  }
  
  return {
    isValid: Object.keys(errors).length === 0,
    errors,
  };
};

/**
 * 配列の検証
 */
export const validateArray = <T>(
  array: T[],
  itemValidator: (item: T, index: number) => string | null,
  fieldName?: string
): string | null => {
  for (let i = 0; i < array.length; i++) {
    const error = itemValidator(array[i], i);
    if (error) {
      return `${fieldName || 'リスト'}の${i + 1}番目の項目: ${error}`;
    }
  }
  
  return null;
};