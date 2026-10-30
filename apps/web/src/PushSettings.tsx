import {usePreferences} from './preferences';
import {useEffect,useState} from 'react';
import {api} from './api';
import {Link} from 'react-router-dom';
import {firebaseConfigured,subscribePush} from './firebase';
interface InstallPrompt extends Event {prompt():Promise<void>;userChoice:Promise<{outcome:string}>}
export function PushSettings({favoriteCount,alertsEnabled}:{favoriteCount:number;alertsEnabled:boolean}){const {t,locale}=usePreferences();
 const [status,setStatus]=useState('');
 const [busy,setBusy]=useState(false);
 const [install,setInstall]=useState<InstallPrompt|null>(null);
 useEffect(()=>{
  const listener=(event:Event)=>{event.preventDefault();setInstall(event as InstallPrompt)};
  window.addEventListener('beforeinstallprompt',listener);
  return()=>window.removeEventListener('beforeinstallprompt',listener);
 },[]);
 async function enable(){
  setBusy(true);setStatus('');
  try{
   if(!import.meta.env.PROD)throw new Error(t("Push requires a production build served over HTTPS (or localhost preview)."));
   const token=await subscribePush();
   await api('/push/register',{token,language:locale});
   setStatus('This device is subscribed. Use Test notification to verify delivery.');
  }catch(error){setStatus((error as Error).message)}finally{setBusy(false)}
 }
 async function action(path:string,message:string){
  setBusy(true);
  try{await api(path,{});setStatus(message)}catch(error){setStatus((error as Error).message)}finally{setBusy(false)}
 }
 return <div className="detail-panel push-settings">
  <h2>{t("Install & notifications")}</h2>
  <p>{t("On iPhone: Share → Add to Home Screen, then open PadelTime from its icon. Installation alone does not allow notifications.")}</p>
  {install&&<button className="button" onClick={async()=>{await install.prompt();await install.userChoice;setInstall(null)}}>{t("Install PadelTime")}</button>}
  {!favoriteCount&&<div className="sync-error" role="status"><span>{t("No players followed on this installation. Test notifications work, but real match alerts need favorites.")}</span> <Link to="/favorites">{t("Choose players")}</Link></div>}
  {!alertsEnabled&&<p role="status">{t("Match alerts are paused. Enable match alerts above to receive real events.")}</p>}
  <p>{t("Players followed on this installation:")} {favoriteCount}. {t("Reinstalling the PWA does not transfer favorites from another installation.")}</p>
  <div className="demo-buttons">
   <button disabled={!firebaseConfigured||busy} onClick={enable}>{t("Enable device notifications")}</button>
   <button disabled={!firebaseConfigured||busy} onClick={()=>action('/push/test','Test submitted. Check device notifications.')}>{t("Test notification")}</button>
   {import.meta.env.VITE_CLOUD_MODE==='true'&&<button disabled={!firebaseConfigured||busy} onClick={()=>action('/push/test-closed','Closed-app test queued. Close the app now; delivery normally takes 3–4 minutes.')}>{t("Closed-app test")}</button>}
   <button disabled={!firebaseConfigured||busy} onClick={()=>action('/push/disable','Device push disabled.')}>{t("Disable device push")}</button>
  </div>
  <p role="status">{t(status)||(!firebaseConfigured?t("Firebase Spark project not configured. Push is not active."):t("Notifications require your permission and a supported browser."))}</p>
 </div>
}
