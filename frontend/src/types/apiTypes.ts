export interface Message {
    role: 'user' | 'assistant';
    content: string;
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