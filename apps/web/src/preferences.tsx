import React,{createContext,useContext,useEffect,useMemo,useState} from 'react';
import {resolveLanguage,resolveTheme,translate,type Language} from './translations';
type Appearance='system'|'dark'|'light';
type LanguagePreference='system'|Language;
function read<T extends string>(key:string,allowed:readonly T[],fallback:T):T{try{const value=JSON.parse(localStorage.getItem(key)||'null');return allowed.includes(value)?value:fallback}catch{return fallback}}
function write(key:string,value:string){try{localStorage.setItem(key,JSON.stringify(value))}catch{/* Preferences still work for this session. */}}
const Preferences=createContext({locale:'en',language:'system' as LanguagePreference,setLanguage:(_v:LanguagePreference)=>{},appearance:'system' as Appearance,setAppearance:(_v:Appearance)=>{},t:(v:string)=>v});
export const usePreferences=()=>useContext(Preferences);
export function PreferencesProvider({children}:{children:React.ReactNode}){
 const [language,setLanguage]=useState<LanguagePreference>(()=>read('pt-language',['system','es','en'],'system'));
 // Old pn-appearance was written automatically as dark, so it cannot identify a manual choice.
 const [appearance,setAppearance]=useState<Appearance>(()=>read('pt-appearance',['system','dark','light'],'system'));
 const [deviceLanguage,setDeviceLanguage]=useState(()=>resolveLanguage(navigator.languages?.length?navigator.languages:[navigator.language]));
 const [dark,setDark]=useState(()=>matchMedia('(prefers-color-scheme: dark)').matches);
 useEffect(()=>{
  const query=matchMedia('(prefers-color-scheme: dark)');
  const themeChanged=()=>setDark(query.matches);
  const languageChanged=()=>setDeviceLanguage(resolveLanguage(navigator.languages?.length?navigator.languages:[navigator.language]));
  query.addEventListener('change',themeChanged);window.addEventListener('languagechange',languageChanged);
  themeChanged();languageChanged();
  return()=>{query.removeEventListener('change',themeChanged);window.removeEventListener('languagechange',languageChanged)};
 },[]);
 const locale=language==='system'?deviceLanguage:language;
 useEffect(()=>{document.documentElement.lang=locale;document.title=locale==='es'?'PadelTime · Llega al primer punto':'PadelTime · Be there for the first point';write('pt-language',language)},[language,locale]);
 useEffect(()=>{const theme=resolveTheme(appearance,dark);document.documentElement.dataset.theme=theme;document.querySelector('meta[name="theme-color"]')?.setAttribute('content',theme==='dark'?'#10130f':'#f5f5ef');write('pt-appearance',appearance)},[appearance,dark]);
 const value=useMemo(()=>({locale,language,setLanguage,appearance,setAppearance,t:(v:string)=>translate(v,locale)}),[locale,language,appearance]);
 return <Preferences.Provider value={value}>{children}</Preferences.Provider>;
}
