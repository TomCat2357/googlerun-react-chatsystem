class ApiClient {
    constructor(apiKey = '') {
        this.apiKey = apiKey;
    }

    async fetchWithAuth(url, options = {}) {
        const urlWithAuth = this.appendApiKey(url);
        return await fetch(urlWithAuth, {
            ...options
        });
    }

    appendApiKey(url) {
        if (!this.apiKey) {
            console.log('appendApiKey result (no API key):', url);
            return url;
        }
        const separator = url.includes('?') ? '&' : '?';
        const urlWithApiKey = `${url}${separator}x-api-key=${this.apiKey}`;
        console.log('appendApiKey result (with API key):', urlWithApiKey);
        return urlWithApiKey;
    }
}

class TokenManager extends ApiClient {
    constructor(apiKey = '') {
        super(apiKey);
        this.currentToken = null;
    }

    async initializeToken(user) {
        try {
            const existingToken = await user.getIdToken(false);
            this.currentToken = existingToken;
            return existingToken;
        } catch (error) {
            console.error('既存トークン取得エラー:', error);
            this.currentToken = null;
            this.tokenExpiration = null;
            throw error;
        }
    }

    async getNewToken(user) {
        try {
            const idToken = await user.getIdToken(true);
            this.currentToken = idToken;
            return idToken;
        } catch (error) {
            console.error('新規トークン取得エラー:', error);
            throw error;
        }
    }

    async sendTokenToServer(token) {
        try {
            const response = await this.fetchWithAuth('/app/refresh-token', {
                method: 'POST',
                headers: {
                    'Authorization': `Bearer ${token}`,
                    'Content-Type': 'application/json'
                },
                credentials: 'include'
            });

            if (!response.ok) {
                throw new Error('トークンの更新に失敗しました');
            }
            return response;
        } catch (error) {
            console.error('トークン送信エラー:', error);
            throw error;
        }
    }

    async refreshToken(user) {
        const newToken = await this.getNewToken(user);
        return await this.sendTokenToServer(newToken);
    }

    getCurrentToken() {
        return this.currentToken;
    }

    isTokenValid() {
        return !!this.currentToken;
    }

    decodeToken(token) {
        try {
            const base64Payload = token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/');
            const pad = base64Payload.length % 4;
            const paddedPayload = pad ? base64Payload + '='.repeat(4 - pad) : base64Payload;
            const payload = JSON.parse(atob(paddedPayload));
            return payload;
        } catch (error) {
            console.error('Token decode error:', error);
            console.log('Token:', token);
            throw error;
        }
    }

    getTokenExpiration(token) {
        const decodedToken = this.decodeToken(token);
        return decodedToken.exp;
    }

    getRemainingTime(token) {
        return this.getTokenExpiration(token) - Date.now() / 1000;
    }
}
class AutoRefreshTokenManager extends TokenManager {
    constructor(firebaseUser, apiKey, refreshThresholdSeconds = 900) {
        super(apiKey);
        this.firebaseUser = firebaseUser;
        this.refreshThresholdMs = refreshThresholdSeconds * 1000;
        this.refreshTimer = null;
    }

    getTimeUntilNextRefresh() {
        const token = this.getCurrentToken();
        if (!token) return null;
        // refreshThresholdMsを考慮した残り時間を計算
        return this.getRemainingTime(token) - (this.refreshThresholdMs / 1000);
    }

    async setupAutoRefresh() {
        try {
            const token = await this.initializeToken(this.firebaseUser);

            if (this.refreshTimer) {
                clearTimeout(this.refreshTimer);
            }

            const currentTime = Date.now();
            const tokenExpirationTime = this.getTokenExpiration(token) * 1000;
            const timeUntilRefresh = tokenExpirationTime - currentTime - this.refreshThresholdMs;

            console.log('Token refresh timing:', {
                currentTime,
                tokenExpirationTime,
                timeUntilRefresh: timeUntilRefresh / 1000 + ' seconds',
                refreshThreshold: this.refreshThresholdMs / 1000 + ' seconds'
            });

            if (timeUntilRefresh > 0) {
                console.log(`Scheduling token refresh in ${timeUntilRefresh / 1000} seconds`);
                this.refreshTimer = setTimeout(async () => {
                    console.log('Executing scheduled token refresh');
                    await this.refreshToken(this.firebaseUser);
                    await this.setupAutoRefresh();
                }, timeUntilRefresh);
            } else {
                console.log('Token needs immediate refresh');
                await this.refreshToken(this.firebaseUser);
                await this.setupAutoRefresh();
            }
        } catch (error) {
            console.error('AutoRefresh setup failed:', error);
            throw error;
        }
    }

    stopAutoRefresh() {
        console.log('Stopping auto refresh timer');
        if (this.refreshTimer) {
            clearTimeout(this.refreshTimer);
            this.refreshTimer = null;
            console.log('Auto refresh timer cleared');
        }
    }
}//const apiClient = new ApiClient(API_GATEWAY_KEY);
// テスト用の呼び出し
// apiClient.fetchWithAuth('/some/endpoint').then(response => console.log(response));

