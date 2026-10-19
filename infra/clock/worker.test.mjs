import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {trigger} from './worker.mjs';
test('signs timestamp, uses fixed HTTPS destination and blocks redirects',async()=>{
 const secret='a'.repeat(32);let sent;
 await trigger({COLLECT_URL:'https://padeltime.vercel.app/api/collect',COLLECT_SECRET:secret},180000,async(url,options)=>{sent=options;return new Response('{}')});
 assert.equal(sent.headers['x-padeltime-signature'],createHmac('sha256',secret).update('180').digest('hex'));
 assert.equal(sent.redirect,'manual');
});
test('rejects unconfigured destination and bad secret',async()=>{
 await assert.rejects(()=>trigger({COLLECT_URL:'http://example.com',COLLECT_SECRET:'x'}));
 await assert.rejects(()=>trigger({COLLECT_URL:'https://padeltime.vercel.app',COLLECT_SECRET:'x'}));
});

test('rejects redirects without following or forwarding the signature',async()=>{
 let calls=0;
 await assert.rejects(()=>trigger({COLLECT_URL:'https://padeltime-two.vercel.app/api/collect',COLLECT_SECRET:'a'.repeat(32)},180000,async(url,options)=>{
  calls++;assert.equal(options.redirect,'manual');
  return new Response(null,{status:302,headers:{Location:'https://other.example/collect'}});
 }),/Collector returned 302/);
 assert.equal(calls,1);
});
