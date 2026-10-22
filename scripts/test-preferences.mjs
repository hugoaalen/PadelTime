import {test} from 'node:test';
import assert from 'node:assert/strict';
import {resolveLanguage,resolveTheme,translate} from '../apps/web/src/translations.ts';
test('browser language order, regional Spanish and unsupported language fallback',()=>{
 assert.equal(resolveLanguage(['es-ES','en-US']),'es');
 assert.equal(resolveLanguage(['es-AR']),'es');
 assert.equal(resolveLanguage(['fr-FR','en-GB','es']),'en');
 assert.equal(resolveLanguage(['fr-FR']),'en');
 assert.equal(resolveLanguage([]),'en');
});
test('system theme tracks device; manual theme overrides it',()=>{
 assert.equal(resolveTheme('system',true),'dark');
 assert.equal(resolveTheme('system',false),'light');
 assert.equal(resolveTheme('light',true),'light');
 assert.equal(resolveTheme('dark',false),'dark');
});
test('navigation, source states and dynamic schedule labels translate without changing names',()=>{
 assert.equal(translate('Settings','es'),'Ajustes');
 assert.equal(translate('Court 2','es'),'Pista 2');
 assert.equal(translate('Not before 18:00','es'),'No antes de las 18:00');
 assert.equal(translate('Settings','en'),'Settings');
 assert.equal(translate('Agustín Tapia','es'),'Agustín Tapia');
});
