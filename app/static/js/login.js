const uiConfig = {
  signInOptions: [
    firebase.auth.GoogleAuthProvider.PROVIDER_ID,
    firebase.auth.EmailAuthProvider.PROVIDER_ID,
  ],
  callbacks: {
    signInSuccessWithAuthResult: function (authResult, _) {
      authResult.user.getIdToken(true).then((idToken) => {
        const tokenManager = new TokenManager(API_GATEWAY_KEY);
        tokenManager
          .sendTokenToServer(idToken)
          .then(async (response) => {
            if (response.ok) {
              const redirectResponse = await tokenManager.fetchWithAuth(
                redirectUrl
              );
              window.location.replace(redirectResponse.url);
            } else {
              throw new Error("トークンの設定に失敗しました");
            }
          })
          .catch((error) => {
            console.error("エラー:", error);
            alert("認証処理中にエラーが発生しました");
          });
      });
      return false;
    },
  },
  signInFlow: "popup",
};

// FirebaseUI開始
ui.start("#firebaseui-auth-container", uiConfig);
