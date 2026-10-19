import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import {trigger} from './worker.mjs';
test('signs timestamp, uses fixed HTTPS destination and blocks redirects',async()=>{
 const secret='a'.repeat(32);let sent;
 await trigger({COLLECT_URL:'https://padeltime.vercel.app/api/collect',COLLECT_SECRET:secret},180000,async(url,options)=>{sent=options;return new Response('{}')});
 assert.equal(sent.headers['x-padeltime-signature'],createHmac('sha256',secret).update('180').digest('hex'));
 assert.equal(sent.redirect,'error');
});
test('rejects unconfigured destination and bad secret',async()=>{
 await assert.rejects(()=>trigger({COLLECT_URL:'http://example.com',COLLECT_SECRET:'x'}));
 await assert.rejects(()=>trigger({COLLECT_URL:'https://padeltime.vercel.app',COLLECT_SECRET:'x'}));
});
