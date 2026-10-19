import {identityToken} from './firebase';
export type Player={id:string;name:string;country:string;rank:number|null};
export type Tournament={id:string;name:string;location:string;category:string;starts:string;ends:string;status:string;source_url?:string};
export type Match={id:string;tournament_id:string;court:string;order:number;order_confirmed:boolean;day:string;schedule_label:string;players:string[];status:string;scores:number[][];official_time:string|null;time_kind:string;round:string;tracking:{state:string;remaining:number|null;previous:Match|null;estimate:{earliest:string;latest:string;label:string}|null}};
export type Notice={id:string;match_id:string;kind:string;message:string;created_at:string};
export async function api<T>(path:string,body?:unknown):Promise<T>{
 const headers:Record<string,string>={};
 if(body)headers['Content-Type']='application/json';
 if(import.meta.env.VITE_CLOUD_MODE==='true'){
  const token=await identityToken();if(token)headers.Authorization='Bearer '+token;
 }
 const r=await fetch(`${import.meta.env.VITE_API_URL||'/api'}${path}`,{method:body?'POST':'GET',headers,body:body?JSON.stringify(body):undefined});
 if(!r.ok){const e=await r.json().catch(()=>({detail:'Connection failed'}));throw new Error(e.detail||'Something went wrong')}
 return r.json();
}

export type Source={demo:boolean;source:string;snapshot:boolean;stale:boolean;fetched_at?:string;date?:string;source_url?:string;warnings:string[];push?:boolean;order_confirmed?:boolean;collector?:{enabled:boolean;state:string;last_success?:string|null;last_error?:string|null;next_attempt?:string|null}};
