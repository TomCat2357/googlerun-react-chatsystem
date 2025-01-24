// ログアウトボタンのイベントリスナー
document.addEventListener("DOMContentLoaded", function () {
    let isInitialized = false;

    async function handleLogout() {
        console.log("ログアウト処理を開始");
        try {
            const user = firebase.auth().currentUser;
            const apiClient = new ApiClient(API_GATEWAY_KEY);
            if (!user) {
                const response = await apiClient.fetchWithAuth("/");
                window.location.replace(response.url);
                return;
            }
            await firebase.auth().signOut();
            console.log("Firebaseサインアウト完了");

            const logoutResponse = await apiClient.fetchWithAuth("/app/logout", {
                method: "POST",
                credentials: "include",
            });

            const redirectResponse = await apiClient.fetchWithAuth("/");
            window.location.replace(redirectResponse.url);
        } catch (error) {
            console.error("ログアウトエラー:", error);
            const errorResponse = await apiClient.fetchWithAuth("/");
            window.location.replace(errorResponse.url);
        }
    }

    function setupLogout() {
        const logoutButton = document.getElementById("logoutButton");
        if (logoutButton) {
            logoutButton.removeEventListener("click", handleLogout);
            logoutButton.addEventListener("click", handleLogout);
        }
    }

    async function initializeApp() {
        if (isInitialized) return;
        try {
            if (!firebase.apps.length) {
                firebase.initializeApp(firebaseConfig);
            }
            setupLogout();
            firebase.auth().onAuthStateChanged((user) => {
                if (user) {
                    setupLogout();
                }
            });
            isInitialized = true;
        } catch (error) {
            console.error("Firebase初期化エラー:", error);
            alert("アプリケーションの初期化に失敗しました");
        }
    }

    initializeApp();
});
