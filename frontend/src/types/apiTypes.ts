export interface Message {
    role: 'user' | 'assistant';
    content: string;
    images?: string[]; // base64エンコード済み画像の配列
  }
  
  export interface ChatRequest {
    messages: Message[];
    model: string;
  }
  
  export interface ChatResponse {
    choices: {
      message: {
        content: string;
      };
    }[];
  }

  // チャット履歴の型定義
  export interface ChatHistory {
    id: number;
    title: string;
    messages: Message[];
    date: string;
    lastPromptDate: string;
  }