class ChatManager {
    constructor() {
        this.messageContainer = document.getElementById('message-container');
        this.messageInput = document.getElementById('message-input');
        this.sendButton = document.getElementById('send-button');
        this.isProcessing = false;
        this.controller = null;
        this.clearButton = document.getElementById('clear-history-button');
        this.modelSelector = document.getElementById('model-selector');
        this.currentSessionId = Date.now(); // 現在のセッションID
        this.messageContainer = document.getElementById('message-container');
            // IndexedDBの設定を追加
            this.dbName = 'ChatHistoryDB';
            this.dbVersion = 1;
            // IndexedDBを初期化してから履歴を読み込む
            this.initIndexedDB().then(() => {
                this.loadChatHistory();
            }).catch(error => {
                console.error('IndexedDB初期化エラー:', error);
            });

        

            // 送信ボタンのイベントリスナーを追加
            this.sendButton.addEventListener('click', () => this.sendMessage());

            this.messageInput.addEventListener('keypress', (e) => {
                if (e.key === 'Enter' && !e.shiftKey) {
                    e.preventDefault();
                    this.sendMessage();
                }
            });

            // クリアボタンのイベントリスナーを追加        
            this.clearButton.addEventListener('click', () => {
                this.clearChat();
            });

            // モデル選択の変更イベントリスナーを追加
            this.modelSelector.addEventListener('change', () => {
                console.log(`Model changed to: ${this.modelSelector.value}`);
                // 必要に応じて新しいモデルに関連する処理を実行
            });

            this.historyList = document.getElementById('chat-history-list');




    }

    // IndexedDBの初期化
    initIndexedDB() {
        this.initPromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(this.dbName, this.dbVersion);

            request.onerror = (event) => {
                console.error('IndexedDBの初期化エラー:', event.target.errorCode);
                reject(event.target.errorCode);
            };

            request.onsuccess = (event) => {
                this.db = event.target.result;
                resolve();
            };

            request.onupgradeneeded = (event) => {
                this.db = event.target.result;
                if (!this.db.objectStoreNames.contains('chatHistory')) {
                    this.db.createObjectStore('chatHistory', { keyPath: 'id' });
                }
            };
        });
        return this.initPromise; // ここでPromiseを返す
    }

    // 現在選択されているモデルを取得するメソッド
    getCurrentModel() {
        return this.modelSelector.value;
    }

    // DOMから現在のチャット履歴を取得
    getChatHistory() {
        const messages = this.messageContainer.children;
        return Array.from(messages).map(msg => ({
            role: msg.classList.contains('user-message') ? 'user' : 'assistant',
            content: msg.textContent
        }));
    }

    // メッセージをUIに追加
    addMessage(content, isUser) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message ${isUser ? 'user-message' : 'assistant-message'}`;
        messageDiv.textContent = content;

        this.messageContainer.appendChild(messageDiv);
        this.messageContainer.scrollTop = this.messageContainer.scrollHeight;

        return messageDiv;
    }

    // 送信ボタンの状態を切り替え
    toggleButton(action) {
        if (action === 'stop') {
            this.sendButton.textContent = '停止';
            this.sendButton.dataset.action = 'stop';
        } else {
            this.sendButton.textContent = '送信';
            this.sendButton.dataset.action = 'send';
        }
    }

    // メッセージの送信処理
    async sendMessage() {
        // 停止ボタンの処理
        if (this.sendButton.dataset.action === 'stop') {
            if (this.controller) {
                this.controller.abort();
                this.toggleButton('send');
                this.isProcessing = false;
                return;
            }
        }

        const message = this.messageInput.value.trim();
        if (!message || this.isProcessing) return;

        this.isProcessing = true;
        this.toggleButton('stop');

        try {
            this.addMessage(message, true);
            this.messageInput.value = '';

            this.controller = new AbortController();
            const signal = this.controller.signal;

            const currentHistory = this.getChatHistory();
            const currentModel = this.getCurrentModel(); // 選択されたモデルを取得

            const apiClient = new ApiClient(API_GATEWAY_KEY);

            const response = await apiClient.fetchWithAuth('/app/chat', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'Accept': 'text/event-stream',
                },
                credentials: 'include',
                signal,
                body: JSON.stringify({
                    messages: currentHistory,
                    model: currentModel // モデル情報を追加
                })
            });

            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }

            const messageDiv = this.addMessage('', false);
            const reader = response.body.getReader();
            const decoder = new TextDecoder();

            while (true) {
                const { done, value } = await reader.read();
                if (done) break;

                const text = decoder.decode(value, { stream: true });
                messageDiv.textContent += text;
                this.messageContainer.scrollTop = this.messageContainer.scrollHeight;
            }

            // 応答が完了したら履歴を保存
            this.saveChatHistory();
        } catch (error) {
            if (error.name !== 'AbortError') {
                console.error('エラー:', error);
                this.addMessage('エラーが発生しました: ' + error.message, false);
            }
        } finally {
            this.isProcessing = false;
            this.toggleButton('send');
            this.controller = null;
            this.messageInput.focus();
        }
    }

    // チャットをクリア
    clearChat() {
        // 進行中の送信があれば停止
        if (this.isProcessing && this.controller) {
            this.controller.abort();
            this.toggleButton('send');
            this.isProcessing = false;
        }

        // 新しいセッションIDを生成
        this.currentSessionId = Date.now();

        // チャット履歴をクリア
        while (this.messageContainer.firstChild) {
            this.messageContainer.removeChild(this.messageContainer.firstChild);
        }

        // 入力欄もクリア
        this.messageInput.value = '';
        this.messageInput.focus();
    }

    // チャット履歴を保存（IndexedDB版）
    saveChatHistory() {
        const history = this.getChatHistory();
        if (history.length === 0) return;

        const historyItem = {
            id: this.currentSessionId, // 現在のセッションIDを使用
            title: history[0].content.slice(0, 12) + '...',
            messages: history,
            date: new Date().toISOString()
        };

        const transaction = this.db.transaction(['chatHistory'], 'readwrite');
        const store = transaction.objectStore('chatHistory');

        store.put(historyItem);

        transaction.oncomplete = () => {
            console.log('チャット履歴が保存されました');
            this.updateHistoryDisplay();
        };

        transaction.onerror = (event) => {
            console.error('チャット履歴の保存中にエラーが発生しました:', event.target.errorCode);
        };
    }

    // チャット履歴を読み込んで表示（IndexedDB版）
    loadChatHistory() {
        const transaction = this.db.transaction(['chatHistory'], 'readonly');
        const store = transaction.objectStore('chatHistory');
        const request = store.getAll();

        request.onsuccess = (event) => {
            this.savedHistory = event.target.result || [];
            this.updateHistoryDisplay();
        };

        request.onerror = (event) => {
            console.error('チャット履歴の読み込み中にエラーが発生しました:', event.target.errorCode);
        };
    }

    // 履歴表示を更新
    updateHistoryDisplay() {
        const transaction = this.db.transaction(['chatHistory'], 'readonly');
        const store = transaction.objectStore('chatHistory');
        const request = store.getAll();

        request.onsuccess = (event) => {
            const savedHistory = event.target.result || [];
            this.historyList.innerHTML = '';

            savedHistory.sort((a, b) => new Date(b.date) - new Date(a.date));

            savedHistory.slice(0, 5).forEach(item => {
                const historyElement = document.createElement('div');
                historyElement.className = 'history-item';
                historyElement.innerHTML = `
                    <div class="history-title">${item.title}</div>
                    <div class="history-date">${new Date(item.date).toLocaleString()}</div>
                `;

                historyElement.addEventListener('click', () => this.restoreChat(item));
                this.historyList.appendChild(historyElement);
            });
        };

        request.onerror = (event) => {
            console.error('履歴表示の更新中にエラーが発生しました:', event.target.errorCode);
        };
    }

    // チャットを復元
    restoreChat(historyItem) {
        this.clearChat();
        this.currentSessionId = historyItem.id; // セッションIDを復元
        historyItem.messages.forEach(msg => {
            this.addMessage(msg.content, msg.role === 'user');
        });
    }
}

// DOMの準備ができたらChatManagerを初期化
document.addEventListener('DOMContentLoaded', () => {
    window.chatManager = new ChatManager();
});

// グローバルな送信関数
function sendMessage() {
    window.chatManager.sendMessage();
}