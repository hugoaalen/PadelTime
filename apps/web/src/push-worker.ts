/// <reference lib="webworker" />
import {initializeApp} from 'firebase/app';
import {getMessaging,onBackgroundMessage} from 'firebase/messaging/sw';
declare const self:ServiceWorkerGlobalScope;
const CACHE='padeltime-shell-v1';
self.addEventListener('install',event=>{event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(['/','/manifest.webmanifest','/icon.svg'])))});
self.addEventListener('activate',event=>{event.waitUntil((async()=>{for(const key of await caches.keys())if(key.startsWith('padeltime-shell-')&&key!==CACHE)await caches.delete(key);await self.clients.claim()})())});
self.addEventListener('fetch',event=>{
 const url=new URL(event.request.url);
 if(event.request.method!=='GET'||url.origin!==self.location.origin||url.pathname.startsWith('/api/'))return;
 if(event.request.mode==='navigate'){
  event.respondWith(fetch(event.request).catch(async()=>await caches.match('/')||Response.error()));return;
 }
 if(url.pathname.startsWith('/assets/')||['/icon.svg','/manifest.webmanifest'].includes(url.pathname)){
  event.respondWith((async()=>{const cached=await caches.match(event.request);if(cached)return cached;const response=await fetch(event.request);if(response.ok){const cache=await caches.open(CACHE);await cache.put(event.request,response.clone())}return response})());
 }
});
// Install click handler before FCM to retain own same-origin navigation policy.
self.addEventListener('notificationclick',event=>{
 event.notification.close();
 const relative=event.notification.data?.url||'/';
 const url=new URL(relative,self.location.origin);
 if(url.origin!==self.location.origin)return;
 event.waitUntil((async()=>{const clients=await self.clients.matchAll({type:'window',includeUncontrolled:true});for(const client of clients){await (client as WindowClient).navigate(url.href);await (client as WindowClient).focus();return}await self.clients.openWindow(url.href)})());
});
const config={apiKey:import.meta.env.VITE_FIREBASE_API_KEY,projectId:import.meta.env.VITE_FIREBASE_PROJECT_ID,messagingSenderId:import.meta.env.VITE_FIREBASE_MESSAGING_SENDER_ID,appId:import.meta.env.VITE_FIREBASE_APP_ID};
if(Object.values(config).every(Boolean)){
 const messaging=getMessaging(initializeApp(config));
 onBackgroundMessage(messaging,async payload=>{
  const data=payload.data||{};
  const cache=await caches.open('padeltime-push-events');
  const key=new Request(new URL('/_push/'+encodeURIComponent(data.event_id||''),self.location.origin));
  if(data.event_id&&await cache.match(key))return;
  await self.registration.showNotification(data.title||'PadelTime',{body:data.body||'Your followed match has an update.',icon:'/icon.svg',tag:data.event_id||'padeltime-update',data:{url:data.url||'/'}});
  if(data.event_id){await cache.put(key,new Response('seen'));const keys=await cache.keys();for(const old of keys.slice(0,Math.max(0,keys.length-100)))await cache.delete(old)}
 });
}
