import {initializeApp,getApps} from 'firebase/app';
import {getAuth,signInAnonymously} from 'firebase/auth';
import {getMessaging,getToken,isSupported} from 'firebase/messaging';
export const firebaseConfig={apiKey:import.meta.env.VITE_FIREBASE_API_KEY,authDomain:import.meta.env.VITE_FIREBASE_AUTH_DOMAIN,projectId:import.meta.env.VITE_FIREBASE_PROJECT_ID,messagingSenderId:import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,appId:import.meta.env.VITE_FIREBASE_APP_ID};
export const firebaseConfigured=Object.values(firebaseConfig).every(Boolean);
export function firebaseApp(){return getApps()[0]||initializeApp(firebaseConfig)}
let signingIn:Promise<unknown>|null=null;
export async function identityToken(){
 if(!firebaseConfigured)return null;
 const auth=getAuth(firebaseApp());
 await auth.authStateReady();
 if(!auth.currentUser){signingIn??=signInAnonymously(auth).finally(()=>{signingIn=null});await signingIn}
 return auth.currentUser!.getIdToken();
}
export async function subscribePush(){
 if(!firebaseConfigured||!import.meta.env.VITE_FIREBASE_VAPID_KEY)throw new Error('Push requires the Firebase Spark project configuration.');
 if(!('Notification' in window)||!('serviceWorker' in navigator)||!('PushManager' in window))throw new Error('Push unsupported here. On iPhone, open the installed Home Screen app.');
 // Permission must be requested by the caller’s explicit button click.
 const permission=await Notification.requestPermission();
 if(permission!=='granted')throw new Error('Notifications not permitted. You can change this in browser settings.');
 if(!await isSupported())throw new Error('Firebase push unsupported in this browser.');
 const registration=await navigator.serviceWorker.ready;
 const token=await getToken(getMessaging(firebaseApp()),{vapidKey:import.meta.env.VITE_FIREBASE_VAPID_KEY,serviceWorkerRegistration:registration});
 if(!token)throw new Error('Could not register this device.');
 return token;
}
