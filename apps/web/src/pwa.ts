export async function registerPwa(){
 if(!('serviceWorker' in navigator))return;
 // Production bundle includes the worker. Development keeps Vite HMR untouched.
 if(import.meta.env.PROD)await navigator.serviceWorker.register('/sw.js',{type:'module'});
}
