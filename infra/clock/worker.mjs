export async function trigger(env, now=Date.now(), request=fetch){
 const url=new URL(env.COLLECT_URL);
 if(url.protocol!=='https:'||!url.hostname.endsWith('.vercel.app')||url.hostname==='REPLACE.vercel.app')throw new Error('Configure an HTTPS Vercel deployment');
 if(!env.COLLECT_SECRET||env.COLLECT_SECRET.length<32)throw new Error('Collector secret must contain at least 32 characters');
 const timestamp=String(Math.floor(now/1000));
 const key=await crypto.subtle.importKey('raw',new TextEncoder().encode(env.COLLECT_SECRET),{name:'HMAC',hash:'SHA-256'},false,['sign']);
 const signature=Array.from(new Uint8Array(await crypto.subtle.sign('HMAC',key,new TextEncoder().encode(timestamp)))).map(b=>b.toString(16).padStart(2,'0')).join('');
 const response=await request(url,{method:'POST',headers:{'x-padeltime-time':timestamp,'x-padeltime-signature':signature},redirect:'error'});
 if(!response.ok)throw new Error('Collector returned '+response.status);
 return response.status;
}
export default {async scheduled(_event,env,ctx){ctx.waitUntil(trigger(env))}};
