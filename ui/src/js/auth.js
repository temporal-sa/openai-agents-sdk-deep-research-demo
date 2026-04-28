// Firebase auth gate.
//
// This module is loaded at the top of every protected page. It hides the
// protected page contents until Firebase resolves auth state, shows a
// brand-styled sign-in card over the gradient background if no user,
// rejects non-@temporal.io accounts, and exposes window.getIdToken() for
// the API client to attach Authorization headers.
//
// Styling lives in ui/src/css/styles.css (.auth-gate / .auth-card / etc).
// window.FIREBASE_CONFIG must be set inline in the host HTML before this
// script is loaded. IT/infra populates the placeholder values from the
// Firebase console.

import { initializeApp } from "https://www.gstatic.com/firebasejs/10.13.2/firebase-app.js";
import {
    getAuth,
    GoogleAuthProvider,
    onAuthStateChanged,
    signInWithPopup,
    signOut as fbSignOut,
} from "https://www.gstatic.com/firebasejs/10.13.2/firebase-auth.js";

const ALLOWED_DOMAIN = "temporal.io";

if (!window.FIREBASE_CONFIG || window.FIREBASE_CONFIG.apiKey === "REPLACE_ME") {
    console.warn(
        "[auth] window.FIREBASE_CONFIG is not populated. " +
        "Auth will not work until IT/infra fills in the Firebase config."
    );
}

const app = initializeApp(window.FIREBASE_CONFIG || {});
const auth = getAuth(app);
const provider = new GoogleAuthProvider();
provider.setCustomParameters({ hd: ALLOWED_DOMAIN });

window.getIdToken = async function getIdToken() {
    if (!auth.currentUser) throw new Error("Not signed in");
    return auth.currentUser.getIdToken();
};

window.signOut = function signOut() {
    return fbSignOut(auth);
};

function setProtectedContentVisibility(visible) {
    const content = document.querySelector(".content-section");
    if (content) content.style.visibility = visible ? "visible" : "hidden";
}

// Reveal the page body (so the gradient renders behind the gate), but
// synchronously hide protected content until auth resolves. Doing both
// before the async onAuthStateChanged callback prevents a flash of the
// chat UI to unauthenticated visitors.
document.body.style.visibility = "visible";
setProtectedContentVisibility(false);

const TEMPORAL_LOGO_SVG = `
    <svg class="temporal-logo" width="48" height="48" viewBox="0 0 48 48" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path d="M32.4154 15.5846C31.2802 7.09512 28.4175 0 24 0C19.5949 0 16.7198 7.09512 15.5846 15.5846C7.09511 16.7198 0 19.5825 0 24C0 28.4051 7.09511 31.2802 15.5846 32.4154C16.7198 40.9049 19.5825 48 24 48C28.4051 48 31.2802 40.9049 32.4154 32.4154C40.9049 31.2802 48 28.4175 48 24C48 19.5825 40.9049 16.7075 32.4154 15.5846ZM15.3131 29.9229C7.18149 28.7506 2.43084 26.0607 2.43084 23.9877C2.43084 21.9147 7.16915 19.2247 15.3131 18.0524C15.128 20.0144 15.0416 22.0134 15.0416 23.9877C15.0416 25.962 15.128 27.9733 15.3131 29.9229ZM24 2.41851C26.073 2.41851 28.763 7.15682 29.9352 15.3008C27.9733 15.1157 25.9743 15.0293 24 15.0293C22.0257 15.0293 20.0267 15.128 18.0648 15.3008C19.237 7.16916 21.927 2.41851 24 2.41851ZM32.6869 29.9229C32.292 29.9846 30.6386 30.1697 30.2314 30.219C30.1943 30.6386 29.9969 32.2797 29.9352 32.6746C28.763 40.8062 26.073 45.5568 24 45.5568C21.927 45.5568 19.237 40.8185 18.0648 32.6746C18.0031 32.2797 17.818 30.6262 17.7686 30.219C17.5835 28.2941 17.4602 26.2211 17.4602 23.9877C17.4602 21.7542 17.5712 19.6936 17.7686 17.7563C19.6936 17.5712 21.7666 17.4478 24 17.4478C26.2334 17.4478 28.2941 17.5589 30.2314 17.7563C30.6509 17.7933 32.292 17.9907 32.6869 18.0524C40.8185 19.2247 45.5691 21.9147 45.5691 23.9877C45.5691 26.0607 40.8185 28.7506 32.6869 29.9229Z" fill="#F8FAFC"/>
    </svg>
`;

const GOOGLE_G_SVG = `
    <svg viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
        <path fill="#FFFFFF" d="M21.35 11.1h-9.17v2.92h5.27c-.23 1.42-1.66 4.16-5.27 4.16-3.17 0-5.76-2.62-5.76-5.86s2.59-5.86 5.76-5.86c1.81 0 3.02.77 3.71 1.43l2.53-2.44C16.95 4.06 14.74 3 12.18 3 6.91 3 2.65 7.26 2.65 12.5S6.91 22 12.18 22c7 0 9.65-4.93 9.65-7.45 0-.51-.05-.9-.13-1.45z"/>
    </svg>
`;

function renderSignInCard(errorMessage) {
    const gate = document.createElement("div");
    gate.id = "auth-gate";
    gate.className = "auth-gate";
    gate.innerHTML = `
        <div class="auth-card">
            ${TEMPORAL_LOGO_SVG}
            <h1 class="auth-heading">Build Durable Agents</h1>
            <p class="auth-subtitle">Internal Temporal demo. Sign in with your @${ALLOWED_DOMAIN} account.</p>
            ${errorMessage ? `<p class="auth-error">${errorMessage}</p>` : ""}
            <button id="auth-signin-btn" class="auth-signin-btn" type="button">
                ${GOOGLE_G_SVG}
                <span>Sign in with Google</span>
            </button>
        </div>
    `;
    document.body.appendChild(gate);
    document.getElementById("auth-signin-btn").addEventListener("click", async () => {
        try {
            await signInWithPopup(auth, provider);
        } catch (err) {
            console.error("[auth] sign-in failed:", err);
        }
    });
}

function renderSignOutButton(email) {
    const btn = document.createElement("button");
    btn.id = "auth-signout-btn";
    btn.className = "auth-signout-btn";
    btn.type = "button";
    btn.textContent = `Sign out (${email})`;
    btn.addEventListener("click", () => fbSignOut(auth));
    document.body.appendChild(btn);
}

function clearGateUI() {
    const gate = document.getElementById("auth-gate");
    if (gate) gate.remove();
    const btn = document.getElementById("auth-signout-btn");
    if (btn) btn.remove();
}

onAuthStateChanged(auth, (user) => {
    clearGateUI();
    if (!user) {
        setProtectedContentVisibility(false);
        renderSignInCard();
        return;
    }
    const email = (user.email || "").toLowerCase();
    if (!email.endsWith("@" + ALLOWED_DOMAIN)) {
        fbSignOut(auth).finally(() => {
            setProtectedContentVisibility(false);
            renderSignInCard(`Access restricted to @${ALLOWED_DOMAIN} accounts.`);
        });
        return;
    }
    setProtectedContentVisibility(true);
    renderSignOutButton(email);
    window.__authReady = true;
});
