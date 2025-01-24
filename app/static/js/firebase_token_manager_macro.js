const _user = firebase.auth().currentUser;
firebase.auth().onAuthStateChanged((_user) => {
    if (_user) {
        autoRefreshTokenManager = new AutoRefreshTokenManager(_user, API_GATEWAY_KEY);
        autoRefreshTokenManager.setupAutoRefresh();
    } else {
        if (autoRefreshTokenManager) {
            autoRefreshTokenManager.stopAutoRefresh();
        }
    }
});