(function(){let e=document.createElement(`link`).relList;if(e&&e.supports&&e.supports(`modulepreload`))return;for(let e of document.querySelectorAll(`link[rel="modulepreload"]`))n(e);new MutationObserver(e=>{for(let t of e)if(t.type===`childList`)for(let e of t.addedNodes)e.tagName===`LINK`&&e.rel===`modulepreload`&&n(e)}).observe(document,{childList:!0,subtree:!0});function t(e){let t={};return e.integrity&&(t.integrity=e.integrity),e.referrerPolicy&&(t.referrerPolicy=e.referrerPolicy),e.crossOrigin===`use-credentials`?t.credentials=`include`:e.crossOrigin===`anonymous`?t.credentials=`omit`:t.credentials=`same-origin`,t}function n(e){if(e.ep)return;e.ep=!0;let n=t(e);fetch(e.href,n)}})();var e=globalThis,t=e.ShadowRoot&&(e.ShadyCSS===void 0||e.ShadyCSS.nativeShadow)&&`adoptedStyleSheets`in Document.prototype&&`replace`in CSSStyleSheet.prototype,n=Symbol(),r=new WeakMap,i=class{constructor(e,t,r){if(this._$cssResult$=!0,r!==n)throw Error("CSSResult is not constructable. Use `unsafeCSS` or `css` instead.");this.cssText=e,this.t=t}get styleSheet(){let e=this.o,n=this.t;if(t&&e===void 0){let t=n!==void 0&&n.length===1;t&&(e=r.get(n)),e===void 0&&((this.o=e=new CSSStyleSheet).replaceSync(this.cssText),t&&r.set(n,e))}return e}toString(){return this.cssText}},a=e=>new i(typeof e==`string`?e:e+``,void 0,n),o=(e,...t)=>new i(e.length===1?e[0]:t.reduce((t,n,r)=>t+(e=>{if(!0===e._$cssResult$)return e.cssText;if(typeof e==`number`)return e;throw Error(`Value passed to 'css' function must be a 'css' function result: `+e+`. Use 'unsafeCSS' to pass non-literal values, but take care to ensure page security.`)})(n)+e[r+1],e[0]),e,n),s=(n,r)=>{if(t)n.adoptedStyleSheets=r.map(e=>e instanceof CSSStyleSheet?e:e.styleSheet);else for(let t of r){let r=document.createElement(`style`),i=e.litNonce;i!==void 0&&r.setAttribute(`nonce`,i),r.textContent=t.cssText,n.appendChild(r)}},c=t?e=>e:e=>e instanceof CSSStyleSheet?(e=>{let t=``;for(let n of e.cssRules)t+=n.cssText;return a(t)})(e):e,{is:l,defineProperty:u,getOwnPropertyDescriptor:d,getOwnPropertyNames:f,getOwnPropertySymbols:p,getPrototypeOf:m}=Object,h=globalThis,ee=h.trustedTypes,te=ee?ee.emptyScript:``,ne=h.reactiveElementPolyfillSupport,g=(e,t)=>e,_={toAttribute(e,t){switch(t){case Boolean:e=e?te:null;break;case Object:case Array:e=e==null?e:JSON.stringify(e)}return e},fromAttribute(e,t){let n=e;switch(t){case Boolean:n=e!==null;break;case Number:n=e===null?null:Number(e);break;case Object:case Array:try{n=JSON.parse(e)}catch{n=null}}return n}},v=(e,t)=>!l(e,t),re={attribute:!0,type:String,converter:_,reflect:!1,useDefault:!1,hasChanged:v};Symbol.metadata??=Symbol(`metadata`),h.litPropertyMetadata??=new WeakMap;var y=class extends HTMLElement{static addInitializer(e){this._$Ei(),(this.l??=[]).push(e)}static get observedAttributes(){return this.finalize(),this._$Eh&&[...this._$Eh.keys()]}static createProperty(e,t=re){if(t.state&&(t.attribute=!1),this._$Ei(),this.prototype.hasOwnProperty(e)&&((t=Object.create(t)).wrapped=!0),this.elementProperties.set(e,t),!t.noAccessor){let n=Symbol(),r=this.getPropertyDescriptor(e,n,t);r!==void 0&&u(this.prototype,e,r)}}static getPropertyDescriptor(e,t,n){let{get:r,set:i}=d(this.prototype,e)??{get(){return this[t]},set(e){this[t]=e}};return{get:r,set(t){let a=r?.call(this);i?.call(this,t),this.requestUpdate(e,a,n)},configurable:!0,enumerable:!0}}static getPropertyOptions(e){return this.elementProperties.get(e)??re}static _$Ei(){if(this.hasOwnProperty(g(`elementProperties`)))return;let e=m(this);e.finalize(),e.l!==void 0&&(this.l=[...e.l]),this.elementProperties=new Map(e.elementProperties)}static finalize(){if(this.hasOwnProperty(g(`finalized`)))return;if(this.finalized=!0,this._$Ei(),this.hasOwnProperty(g(`properties`))){let e=this.properties,t=[...f(e),...p(e)];for(let n of t)this.createProperty(n,e[n])}let e=this[Symbol.metadata];if(e!==null){let t=litPropertyMetadata.get(e);if(t!==void 0)for(let[e,n]of t)this.elementProperties.set(e,n)}this._$Eh=new Map;for(let[e,t]of this.elementProperties){let n=this._$Eu(e,t);n!==void 0&&this._$Eh.set(n,e)}this.elementStyles=this.finalizeStyles(this.styles)}static finalizeStyles(e){let t=[];if(Array.isArray(e)){let n=new Set(e.flat(1/0).reverse());for(let e of n)t.unshift(c(e))}else e!==void 0&&t.push(c(e));return t}static _$Eu(e,t){let n=t.attribute;return!1===n?void 0:typeof n==`string`?n:typeof e==`string`?e.toLowerCase():void 0}constructor(){super(),this._$Ep=void 0,this.isUpdatePending=!1,this.hasUpdated=!1,this._$Em=null,this._$Ev()}_$Ev(){this._$ES=new Promise(e=>this.enableUpdating=e),this._$AL=new Map,this._$E_(),this.requestUpdate(),this.constructor.l?.forEach(e=>e(this))}addController(e){(this._$EO??=new Set).add(e),this.renderRoot!==void 0&&this.isConnected&&e.hostConnected?.()}removeController(e){this._$EO?.delete(e)}_$E_(){let e=new Map,t=this.constructor.elementProperties;for(let n of t.keys())this.hasOwnProperty(n)&&(e.set(n,this[n]),delete this[n]);e.size>0&&(this._$Ep=e)}createRenderRoot(){let e=this.shadowRoot??this.attachShadow(this.constructor.shadowRootOptions);return s(e,this.constructor.elementStyles),e}connectedCallback(){this.renderRoot??=this.createRenderRoot(),this.enableUpdating(!0),this._$EO?.forEach(e=>e.hostConnected?.())}enableUpdating(e){}disconnectedCallback(){this._$EO?.forEach(e=>e.hostDisconnected?.())}attributeChangedCallback(e,t,n){this._$AK(e,n)}_$ET(e,t){let n=this.constructor.elementProperties.get(e),r=this.constructor._$Eu(e,n);if(r!==void 0&&!0===n.reflect){let i=(n.converter?.toAttribute===void 0?_:n.converter).toAttribute(t,n.type);this._$Em=e,i==null?this.removeAttribute(r):this.setAttribute(r,i),this._$Em=null}}_$AK(e,t){let n=this.constructor,r=n._$Eh.get(e);if(r!==void 0&&this._$Em!==r){let e=n.getPropertyOptions(r),i=typeof e.converter==`function`?{fromAttribute:e.converter}:e.converter?.fromAttribute===void 0?_:e.converter;this._$Em=r;let a=i.fromAttribute(t,e.type);this[r]=a??this._$Ej?.get(r)??a,this._$Em=null}}requestUpdate(e,t,n,r=!1,i){if(e!==void 0){let a=this.constructor;if(!1===r&&(i=this[e]),n??=a.getPropertyOptions(e),!((n.hasChanged??v)(i,t)||n.useDefault&&n.reflect&&i===this._$Ej?.get(e)&&!this.hasAttribute(a._$Eu(e,n))))return;this.C(e,t,n)}!1===this.isUpdatePending&&(this._$ES=this._$EP())}C(e,t,{useDefault:n,reflect:r,wrapped:i},a){n&&!(this._$Ej??=new Map).has(e)&&(this._$Ej.set(e,a??t??this[e]),!0!==i||a!==void 0)||(this._$AL.has(e)||(this.hasUpdated||n||(t=void 0),this._$AL.set(e,t)),!0===r&&this._$Em!==e&&(this._$Eq??=new Set).add(e))}async _$EP(){this.isUpdatePending=!0;try{await this._$ES}catch(e){Promise.reject(e)}let e=this.scheduleUpdate();return e!=null&&await e,!this.isUpdatePending}scheduleUpdate(){return this.performUpdate()}performUpdate(){if(!this.isUpdatePending)return;if(!this.hasUpdated){if(this.renderRoot??=this.createRenderRoot(),this._$Ep){for(let[e,t]of this._$Ep)this[e]=t;this._$Ep=void 0}let e=this.constructor.elementProperties;if(e.size>0)for(let[t,n]of e){let{wrapped:e}=n,r=this[t];!0!==e||this._$AL.has(t)||r===void 0||this.C(t,void 0,n,r)}}let e=!1,t=this._$AL;try{e=this.shouldUpdate(t),e?(this.willUpdate(t),this._$EO?.forEach(e=>e.hostUpdate?.()),this.update(t)):this._$EM()}catch(t){throw e=!1,this._$EM(),t}e&&this._$AE(t)}willUpdate(e){}_$AE(e){this._$EO?.forEach(e=>e.hostUpdated?.()),this.hasUpdated||(this.hasUpdated=!0,this.firstUpdated(e)),this.updated(e)}_$EM(){this._$AL=new Map,this.isUpdatePending=!1}get updateComplete(){return this.getUpdateComplete()}getUpdateComplete(){return this._$ES}shouldUpdate(e){return!0}update(e){this._$Eq&&=this._$Eq.forEach(e=>this._$ET(e,this[e])),this._$EM()}updated(e){}firstUpdated(e){}};y.elementStyles=[],y.shadowRootOptions={mode:`open`},y[g(`elementProperties`)]=new Map,y[g(`finalized`)]=new Map,ne?.({ReactiveElement:y}),(h.reactiveElementVersions??=[]).push(`2.1.2`);var b=globalThis,ie=e=>e,x=b.trustedTypes,ae=x?x.createPolicy(`lit-html`,{createHTML:e=>e}):void 0,oe=`$lit$`,S=`lit$${Math.random().toFixed(9).slice(2)}$`,C=`?`+S,se=`<${C}>`,w=document,T=()=>w.createComment(``),E=e=>e===null||typeof e!=`object`&&typeof e!=`function`,D=Array.isArray,ce=e=>D(e)||typeof e?.[Symbol.iterator]==`function`,O=`[ 	
\f\r]`,k=/<(?:(!--|\/[^a-zA-Z])|(\/?[a-zA-Z][^>\s]*)|(\/?$))/g,le=/-->/g,ue=/>/g,A=RegExp(`>|${O}(?:([^\\s"'>=/]+)(${O}*=${O}*(?:[^ \t\n\f\r"'\`<>=]|("|')|))|$)`,`g`),de=/'/g,fe=/"/g,pe=/^(?:script|style|textarea|title)$/i,j=(e=>(t,...n)=>({_$litType$:e,strings:t,values:n}))(1),M=Symbol.for(`lit-noChange`),N=Symbol.for(`lit-nothing`),me=new WeakMap,P=w.createTreeWalker(w,129);function he(e,t){if(!D(e)||!e.hasOwnProperty(`raw`))throw Error(`invalid template strings array`);return ae===void 0?t:ae.createHTML(t)}var ge=(e,t)=>{let n=e.length-1,r=[],i,a=t===2?`<svg>`:t===3?`<math>`:``,o=k;for(let t=0;t<n;t++){let n=e[t],s,c,l=-1,u=0;for(;u<n.length&&(o.lastIndex=u,c=o.exec(n),c!==null);)u=o.lastIndex,o===k?c[1]===`!--`?o=le:c[1]===void 0?c[2]===void 0?c[3]!==void 0&&(o=A):(pe.test(c[2])&&(i=RegExp(`</`+c[2],`g`)),o=A):o=ue:o===A?c[0]===`>`?(o=i??k,l=-1):c[1]===void 0?l=-2:(l=o.lastIndex-c[2].length,s=c[1],o=c[3]===void 0?A:c[3]===`"`?fe:de):o===fe||o===de?o=A:o===le||o===ue?o=k:(o=A,i=void 0);let d=o===A&&e[t+1].startsWith(`/>`)?` `:``;a+=o===k?n+se:l>=0?(r.push(s),n.slice(0,l)+oe+n.slice(l)+S+d):n+S+(l===-2?t:d)}return[he(e,a+(e[n]||`<?>`)+(t===2?`</svg>`:t===3?`</math>`:``)),r]},F=class e{constructor({strings:t,_$litType$:n},r){let i;this.parts=[];let a=0,o=0,s=t.length-1,c=this.parts,[l,u]=ge(t,n);if(this.el=e.createElement(l,r),P.currentNode=this.el.content,n===2||n===3){let e=this.el.content.firstChild;e.replaceWith(...e.childNodes)}for(;(i=P.nextNode())!==null&&c.length<s;){if(i.nodeType===1){if(i.hasAttributes())for(let e of i.getAttributeNames())if(e.endsWith(oe)){let t=u[o++],n=i.getAttribute(e).split(S),r=/([.?@])?(.*)/.exec(t);c.push({type:1,index:a,name:r[2],strings:n,ctor:r[1]===`.`?ve:r[1]===`?`?ye:r[1]===`@`?be:R}),i.removeAttribute(e)}else e.startsWith(S)&&(c.push({type:6,index:a}),i.removeAttribute(e));if(pe.test(i.tagName)){let e=i.textContent.split(S),t=e.length-1;if(t>0){i.textContent=x?x.emptyScript:``;for(let n=0;n<t;n++)i.append(e[n],T()),P.nextNode(),c.push({type:2,index:++a});i.append(e[t],T())}}}else if(i.nodeType===8)if(i.data===C)c.push({type:2,index:a});else{let e=-1;for(;(e=i.data.indexOf(S,e+1))!==-1;)c.push({type:7,index:a}),e+=S.length-1}a++}}static createElement(e,t){let n=w.createElement(`template`);return n.innerHTML=e,n}};function I(e,t,n=e,r){if(t===M)return t;let i=r===void 0?n._$Cl:n._$Co?.[r],a=E(t)?void 0:t._$litDirective$;return i?.constructor!==a&&(i?._$AO?.(!1),a===void 0?i=void 0:(i=new a(e),i._$AT(e,n,r)),r===void 0?n._$Cl=i:(n._$Co??=[])[r]=i),i!==void 0&&(t=I(e,i._$AS(e,t.values),i,r)),t}var _e=class{constructor(e,t){this._$AV=[],this._$AN=void 0,this._$AD=e,this._$AM=t}get parentNode(){return this._$AM.parentNode}get _$AU(){return this._$AM._$AU}u(e){let{el:{content:t},parts:n}=this._$AD,r=(e?.creationScope??w).importNode(t,!0);P.currentNode=r;let i=P.nextNode(),a=0,o=0,s=n[0];for(;s!==void 0;){if(a===s.index){let t;s.type===2?t=new L(i,i.nextSibling,this,e):s.type===1?t=new s.ctor(i,s.name,s.strings,this,e):s.type===6&&(t=new xe(i,this,e)),this._$AV.push(t),s=n[++o]}a!==s?.index&&(i=P.nextNode(),a++)}return P.currentNode=w,r}p(e){let t=0;for(let n of this._$AV)n!==void 0&&(n.strings===void 0?n._$AI(e[t]):(n._$AI(e,n,t),t+=n.strings.length-2)),t++}},L=class e{get _$AU(){return this._$AM?._$AU??this._$Cv}constructor(e,t,n,r){this.type=2,this._$AH=N,this._$AN=void 0,this._$AA=e,this._$AB=t,this._$AM=n,this.options=r,this._$Cv=r?.isConnected??!0}get parentNode(){let e=this._$AA.parentNode,t=this._$AM;return t!==void 0&&e?.nodeType===11&&(e=t.parentNode),e}get startNode(){return this._$AA}get endNode(){return this._$AB}_$AI(e,t=this){e=I(this,e,t),E(e)?e===N||e==null||e===``?(this._$AH!==N&&this._$AR(),this._$AH=N):e!==this._$AH&&e!==M&&this._(e):e._$litType$===void 0?e.nodeType===void 0?ce(e)?this.k(e):this._(e):this.T(e):this.$(e)}O(e){return this._$AA.parentNode.insertBefore(e,this._$AB)}T(e){this._$AH!==e&&(this._$AR(),this._$AH=this.O(e))}_(e){this._$AH!==N&&E(this._$AH)?this._$AA.nextSibling.data=e:this.T(w.createTextNode(e)),this._$AH=e}$(e){let{values:t,_$litType$:n}=e,r=typeof n==`number`?this._$AC(e):(n.el===void 0&&(n.el=F.createElement(he(n.h,n.h[0]),this.options)),n);if(this._$AH?._$AD===r)this._$AH.p(t);else{let e=new _e(r,this),n=e.u(this.options);e.p(t),this.T(n),this._$AH=e}}_$AC(e){let t=me.get(e.strings);return t===void 0&&me.set(e.strings,t=new F(e)),t}k(t){D(this._$AH)||(this._$AH=[],this._$AR());let n=this._$AH,r,i=0;for(let a of t)i===n.length?n.push(r=new e(this.O(T()),this.O(T()),this,this.options)):r=n[i],r._$AI(a),i++;i<n.length&&(this._$AR(r&&r._$AB.nextSibling,i),n.length=i)}_$AR(e=this._$AA.nextSibling,t){for(this._$AP?.(!1,!0,t);e!==this._$AB;){let t=ie(e).nextSibling;ie(e).remove(),e=t}}setConnected(e){this._$AM===void 0&&(this._$Cv=e,this._$AP?.(e))}},R=class{get tagName(){return this.element.tagName}get _$AU(){return this._$AM._$AU}constructor(e,t,n,r,i){this.type=1,this._$AH=N,this._$AN=void 0,this.element=e,this.name=t,this._$AM=r,this.options=i,n.length>2||n[0]!==``||n[1]!==``?(this._$AH=Array(n.length-1).fill(new String),this.strings=n):this._$AH=N}_$AI(e,t=this,n,r){let i=this.strings,a=!1;if(i===void 0)e=I(this,e,t,0),a=!E(e)||e!==this._$AH&&e!==M,a&&(this._$AH=e);else{let r=e,o,s;for(e=i[0],o=0;o<i.length-1;o++)s=I(this,r[n+o],t,o),s===M&&(s=this._$AH[o]),a||=!E(s)||s!==this._$AH[o],s===N?e=N:e!==N&&(e+=(s??``)+i[o+1]),this._$AH[o]=s}a&&!r&&this.j(e)}j(e){e===N?this.element.removeAttribute(this.name):this.element.setAttribute(this.name,e??``)}},ve=class extends R{constructor(){super(...arguments),this.type=3}j(e){this.element[this.name]=e===N?void 0:e}},ye=class extends R{constructor(){super(...arguments),this.type=4}j(e){this.element.toggleAttribute(this.name,!!e&&e!==N)}},be=class extends R{constructor(e,t,n,r,i){super(e,t,n,r,i),this.type=5}_$AI(e,t=this){if((e=I(this,e,t,0)??N)===M)return;let n=this._$AH,r=e===N&&n!==N||e.capture!==n.capture||e.once!==n.once||e.passive!==n.passive,i=e!==N&&(n===N||r);r&&this.element.removeEventListener(this.name,this,n),i&&this.element.addEventListener(this.name,this,e),this._$AH=e}handleEvent(e){typeof this._$AH==`function`?this._$AH.call(this.options?.host??this.element,e):this._$AH.handleEvent(e)}},xe=class{constructor(e,t,n){this.element=e,this.type=6,this._$AN=void 0,this._$AM=t,this.options=n}get _$AU(){return this._$AM._$AU}_$AI(e){I(this,e)}},Se={M:oe,P:S,A:C,C:1,L:ge,R:_e,D:ce,V:I,I:L,H:R,N:ye,U:be,B:ve,F:xe},Ce=b.litHtmlPolyfillSupport;Ce?.(F,L),(b.litHtmlVersions??=[]).push(`3.3.2`);var we=(e,t,n)=>{let r=n?.renderBefore??t,i=r._$litPart$;if(i===void 0){let e=n?.renderBefore??null;r._$litPart$=i=new L(t.insertBefore(T(),e),e,void 0,n??{})}return i._$AI(e),i},z=globalThis,B=class extends y{constructor(){super(...arguments),this.renderOptions={host:this},this._$Do=void 0}createRenderRoot(){let e=super.createRenderRoot();return this.renderOptions.renderBefore??=e.firstChild,e}update(e){let t=this.render();this.hasUpdated||(this.renderOptions.isConnected=this.isConnected),super.update(e),this._$Do=we(t,this.renderRoot,this.renderOptions)}connectedCallback(){super.connectedCallback(),this._$Do?.setConnected(!0)}disconnectedCallback(){super.disconnectedCallback(),this._$Do?.setConnected(!1)}render(){return M}};B._$litElement$=!0,B.finalized=!0,z.litElementHydrateSupport?.({LitElement:B});var Te=z.litElementPolyfillSupport;Te?.({LitElement:B}),(z.litElementVersions??=[]).push(`4.2.2`);var V=e=>(t,n)=>{n===void 0?customElements.define(e,t):n.addInitializer(()=>{customElements.define(e,t)})},Ee={attribute:!0,type:String,converter:_,reflect:!1,hasChanged:v},De=(e=Ee,t,n)=>{let{kind:r,metadata:i}=n,a=globalThis.litPropertyMetadata.get(i);if(a===void 0&&globalThis.litPropertyMetadata.set(i,a=new Map),r===`setter`&&((e=Object.create(e)).wrapped=!0),a.set(n.name,e),r===`accessor`){let{name:r}=n;return{set(n){let i=t.get.call(this);t.set.call(this,n),this.requestUpdate(r,i,e,!0,n)},init(t){return t!==void 0&&this.C(r,void 0,e,t),t}}}if(r===`setter`){let{name:r}=n;return function(n){let i=this[r];t.call(this,n),this.requestUpdate(r,i,e,!0,n)}}throw Error(`Unsupported decorator location: `+r)};function H(e){return(t,n)=>typeof n==`object`?De(e,t,n):((e,t,n)=>{let r=t.hasOwnProperty(n);return t.constructor.createProperty(n,e),r?Object.getOwnPropertyDescriptor(t,n):void 0})(e,t,n)}function U(e){return H({...e,state:!0,attribute:!1})}var W=o`
    :host {
        /* TYPOGRAPHY */
        --form-font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
        --form-font-size-base: var(--font-size-base, 1rem);
        --form-font-size-h1: var(--font-size-h1, 1.8rem);
        --form-font-size-h2: var(--font-size-h2, 1.4rem);
        --form-font-size-label: var(--font-size-label, 0.9rem);
        --form-font-size-description: var(--font-size-description, 0.85rem);

        /* COLOURS */
        --mires-color-primary-parts: var(--color-primary-parts, 273 74% 53%);
        --mires-color-secondary-parts: var(--color-secondary-parts, 210 100% 50%);
        --mires-color-text-parts: var(--color-text-parts, 0 0% 20%);
        --mires-color-background-parts: var(--color-background-parts, 0 0% 100%);

        --mires-color-text: var(--color-text, hsl(var(--mires-color-text-parts)));
        --mires-color-background: var(--color-background, hsl(var(--mires-color-background-parts)));
        --mires-color-background-darker: var(--color-background-darker, hsl(from hsl(var(--mires-color-background-parts)) h s calc(l / .5)));

        --mires-form-color-text: hsl(var(--mires-color-text-parts));
        --mires-form-color-input-text: var(--color-input-text, #111);
        --mires-form-color-text-secondary: var(--color-text-secondary, #555); /* För beskrivningar */
        --mires-form-color-text-label: var(--color-text-label, #111);
        --mires-form-color-background: var(--form-color-background, var(--mires-color-background, hsl(0, 0%, 100%)));
        --mires-form-color-background-input-base: var(--color-background-input-base, #ffffff);
        --mires-form-color-background-input-focus: var(--color-background-input-focus, #ffffff);
        --mires-form-color-background-input-ok: var(--color-background-input-base, #b9fb9f);
        --mires-form-color-background-input-ok-focus: var(--color-background-input-focus, #b9fb9f);
        --mires-form-color-background-section: var(--color-background-section, #f9f9f9);
        --mires-form-color-border: var(--color-border, #ccc);
        --mires-form-color-border-focus: var(--form-color-accent);

        /* ACCENT COLOUR (Buttons, active tabs, etc.) */
        --mires-color-primary: var(--color-primary, hsl(var(--mires-color-primary-parts)));
        --mires-color-primary-hover: var(--color-primary-hover, hsl(var(--color-primary-parts, 273 74% 53%) / .5)));
        --color-secondary: hsl(var(--mires-color-secondary-parts));
        --color-secondary-hover: hsl(var(--mires-color-secondary-parts) / .5);
        --form-color-success: var(--color-success, #28a745);
        --form-color-success-darker: var(--color-success-darker, #1e7e34);
        --form-color-success-text: var(--color-success-text, #ffffff);
        --form-color-warning: var(--color-warning, #fbb34e);
        --form-color-warning-darker: var(--color-warning-darker, #fea429);
        --form-color-warning-text: var(--color-warning-text, #ffffff);
        --form-color-neutral: var(--color-neutral, #6c757d);
        --form-color-neutral-darker: var(--color-neutral-darker, #5a6268);
        --form-color-neutral-text: var(--color-neutral-text, #ffffff);
        --form-color-error: var(--color-error, #dc3545);
        --form-color-error-lighter: var(--color-error-lighter, #fa5969);
        --form-color-error-text: var(--color-error-text, #721c24);

        /* STATUS COLOUR (for tolerances) */
        --form-color-required-star: var(--color-required-star, #f98989);
        --form-color-within-tolerance-border: var(--color-within-tolerance-border, #8fff8f);
        --form-color-within-tolerance-background: var(--color-within-tolerance-background, #b9fb9f);
        --form-color-within-tolerance-input-text: var(--color-within-tolerance-input-text, #214521);
        --form-color-within-tolerance-text: var(--color-within-tolerance-text, #3c763d);
        --form-color-out-of-tolerance-border: var(--color-out-of-tolerance-border, #fdf8b2);
        --form-color-out-of-tolerance-background: var(--color-background-input-base, #fff894);
        --form-color-out-of-tolerance-text: var(--color-out-of-tolerance-text, #d9534f);
        --form-color-has-error-border: var(--color-has-error-border, var(--form-color-out-of-tolerance-text));
        --form-color-has-error-background: var(--color-has-error-background, #d58d8b);
        --form-color-out-of-tolerance-warning: var(--form-color-out-of-tolerance-text, yellow);

        /* LAYOUT */
        --form-border-radius: var(--border-radius, 4px);
        --form-spacing-medium: var(--spacing-medium, 1rem);
        --form-spacing-large: var(--spacing-large, 1.5rem);
        --form-button-padding: var(--button-padding, 0.3rem 1rem);

        /* =============================================
        // 2. MAPPNING TO SHOELACE DESIGN TOKENS
        // ============================================= */

        --sl-color-primary-500: var(--form-color-accent);
        --sl-color-primary-600: var(--form-color-accent-darker);

        --sl-color-success-500: var(--form-color-success);
        --sl-color-success-600: var(--form-color-success-darker);

        --sl-color-neutral-500: var(--form-color-neutral);
        --sl-color-neutral-600: var(--form-color-neutral-darker);

        --sl-color-warning-500: var(--form-color-warning);
        --sl-color-warning-600: var(--form-color-warning-darker);

        --sl-font-sans: var(--form-font-family);

        --sl-input-border-color: var(--mires-form-color-border);
        --sl-input-border-color-focus: var(--mires-form-color-border-focus);
        --sl-input-border-radius-medium: var(--form-border-radius);

        /* =============================================
        // 3. GLOBAL STYLING FÖR DENNA KOMPONENT
        // ============================================= */

        font-family: var(--form-font-family, "sans-serif");
        font-size: var(--form-font-size-base);
        color: var(--mires-form-color-text);
        background-color: var(--mires-form-color-background);
        display: block;
        --border: 1px solid var(--mires-form-color-border);
        --border-radius: var(--form-border-radius);
        padding: var(--form-spacing-large);
    }


`;o`
    .btn {
        padding: var
    }
    .btn {
      background: var(--primary);
      color: white;
      border: none;
      padding: 8px 16px;
      border-radius: 6px;
      font-weight: 500;
      cursor: pointer;
      transition: background 0.2s;
    }

    .btn:hover {
      background: var(--primary-hover);
    }
`;function G(e,t,n,r){var i=arguments.length,a=i<3?t:r===null?r=Object.getOwnPropertyDescriptor(t,n):r,o;if(typeof Reflect==`object`&&typeof Reflect.decorate==`function`)a=Reflect.decorate(e,t,n,r);else for(var s=e.length-1;s>=0;s--)(o=e[s])&&(a=(i<3?o(a):i>3?o(t,n,a):o(t,n))||a);return i>3&&a&&Object.defineProperty(t,n,a),a}var K=class extends B{constructor(...e){super(...e),this.apiUri=``,this.columnListApiUri=``,this.bookmarkApiUri=``,this.bookmarkId=``,this.monitorTitle=`Monitor`,this.monitorFilter={gender:[],age:{min:0,max:200,selected_min:0,selected_max:200,include_null:!0},studyDescription:[],seriesDescription:[]},this._tableData={columns:[]},this._availableColumns=[{id:`patientName`,title:`Patient Name`,dataType:`string`},{id:`patientAge`,title:`Patient Age`,dataType:`number`},{id:`modality`,title:`Modality`,dataType:`string`},{id:`studyDate`,title:`Study Date`,dataType:`date`},{id:`studyTime`,title:`Study Time`,dataType:`time`}],this._selectedColumns=[]}async connectedCallback(){super.connectedCallback(),await this.fetchAvailableColumns()}async fetchAvailableColumns(){if(this.columnListApiUri)try{let e=await fetch(this.columnListApiUri);e.ok?this._availableColumns=await e.json():console.error(`Failed to fetch columns:`,e.statusText)}catch(e){console.error(`Error fetching columns:`,e)}}static{this.styles=[W,o`
        #monitor-container {
            display: flex;
            flex-direction: column;
            gap: 1rem;
            position: relative;
        }
        
        miqa-monitor-filter {
            position: relative;
            z-index: 10;
            display: block;
            margin-bottom: 1rem;
            padding: 0;
        }
        
        miqa-monitor-table {
            padding: 0;
            position: relative;
            z-index: 1;
        }
        `]}render(){return j`
        <div id="monitor-container">
          <h1>${this.monitorTitle}</h1>
          <miqa-monitor-columns
            .availableColumns=${this._availableColumns}
            .selectedColumns=${this._selectedColumns}
            @column-selection-changed="${e=>this._selectedColumns=e.detail.selectedColumns}"
          ></miqa-monitor-columns>
          <miqa-monitor-filter
            .monitorFilter=${this.monitorFilter}
          ></miqa-monitor-filter>
          <miqa-monitor-table
            .selectedColumns=${this._selectedColumns}
            .tableData=${this._tableData}
          ></miqa-monitor-table>
        </div>
      `}};G([H({type:String})],K.prototype,`apiUri`,void 0),G([H({type:String})],K.prototype,`columnListApiUri`,void 0),G([H({type:String})],K.prototype,`bookmarkApiUri`,void 0),G([H({type:String})],K.prototype,`bookmarkId`,void 0),G([H({type:String})],K.prototype,`monitorTitle`,void 0),G([U()],K.prototype,`monitorFilter`,void 0),G([U()],K.prototype,`_tableData`,void 0),G([U()],K.prototype,`_availableColumns`,void 0),G([U()],K.prototype,`_selectedColumns`,void 0),K=G([V(`miqa-monitor`)],K);var Oe=j`<svg class="MuiSvgIcon-root MuiSvgIcon-fontSizeMedium css-1phnduy" focusable="false" aria-hidden="true" viewBox="0 0 24 24"><path d="M7.41 8.59 12 13.17l4.59-4.58L18 10l-6 6-6-6z"></path></svg>`,ke=j`<svg class="MuiSvgIcon-root MuiSvgIcon-fontSizeMedium css-1phnduy" focusable="false" aria-hidden="true" viewBox="0 0 24 24"><path d="M8.59 16.59 13.17 12 8.59 7.41 10 6l6 6-6 6z"></path></svg>`,Ae=j`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-panel-right-open h-3.5 w-3.5"><rect width="18" height="18" x="3" y="3" rx="2"></rect><path d="M15 3v18"></path><path d="m10 15-3-3 3-3"></path></svg>`,q=j`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-plus h-3 w-3"><path d="M5 12h14"></path><path d="M12 5v14"></path></svg>`,J=class extends B{constructor(...e){super(...e),this.availableColumns=[],this.selectedColumns=[],this._collapsed=!0,this._showContent=!1,this._draggedColumnId=null,this._dragOverColumnId=null,this._visibleAvailableColumns=[],this._visibleSelectedColumns=[]}static{this.styles=[W,o`
        :host {
            position: fixed;
            top: 0;
            right: 0;
            bottom: 0;
            z-index: 1000;
            pointer-events: none;
            padding: 0;
            border: none;
        }

        .drawer {
            position: absolute;
            top: 0;
            right: 0;
            bottom: 0;
            width: 30rem;
            background-color: var(--mires-color-background-darker);
            box-shadow: -2px 0 5px rgba(0, 0, 0, 0.2);
            transition: transform 0.2s ease-in-out;
            display: flex;
            flex-direction: column;
            pointer-events: auto;
        }
            
        input {
            width: calc(100% - 0.8rem);
            padding: 0.5rem;
            box-sizing: border-box;
        }

        .drawer.collapsed {
            transform: translateX(100%);
            box-shadow: none;
        }
            
        .drawer button svg {
            fill: none;
            stroke: currentColor;
        }
            
        .drawer.expanded button svg {
            transform: rotate(180deg);
        }
            
        .toggle-button {
            position: absolute;
            left: -2.5em;
            top: 50%;
            transform: translateY(-50%);
            width: 2.5em;
            height: 3.75em;
            background-color: var(--mires-color-background-darker);
            border: 1px solid #ccc;
            border-right: none;
            border-radius: 1rem 0 0 1rem;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            box-shadow: -2px 0 5px rgba(0, 0, 0, 0.1);
        }

        .toggle-button:hover {
            background-color: hsl(from hsl(var(--mires-color-primary-parts)) h s calc(l / .5));
        }

        .drawer-content {
            padding: 16px;
            overflow-y: auto;
            flex-grow: 1;
        }
            
        .column-lists-container {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 0.8rem;
        }
            
        .btn-list-container  {
            margin-top: 0.5rem;
            display: flex;
            flex-direction: column;
            gap: 0.1rem;
        }
        
        .selected-columns-col {
            border-right: 1px solid var(--color-border, #ffff);
        }

        .column-btn {
            background-color: var(--mires-form-input-background);
            display: block;
            width: 95%;
            padding: 0.5rem 1rem;
            margin-bottom: 4px;
            text-align: left;
            cursor: pointer;
            border: 1px solid #ccc;
            box-sizing: border-box;
            border-radius: 1rem;
        }

        .selected-column-btn {
            cursor: grab;
            background-color: var(--color-primary);
        }

        .selected-column-btn:active {
            cursor: grabbing;
        }

        .selected-column-btn.dragging {
            opacity: 0.5;
        }

        .selected-column-btn.drag-over {
            border-top: 2px solid #007bff;
        }

        h3, h4 {
            margin-top: 0;
        }
    `]}willUpdate(e){(e.has(`availableColumns`)||e.has(`selectedColumns`)||e.has(`columnsOrder`))&&this._filterAvailableColumns(new Event(`input`))}render(){return j`
            <div class="drawer ${this._collapsed?`collapsed`:`expanded`}" @transitionend="${this._handleTransitionEnd}">
                <button class="toggle-button" @click="${this._toggleCollapsed}">
                    ${Ae}
                </button>
                ${this._showContent?j`
                    <div class="drawer-content">
                        <div class="column-list-header">
                            <h3>Columns</h3>
                        </div>
                        <div class="column-lists-container">
                            <div class="selected-columns-col">
                                <h4>Selected</h4>
                                <input type="text" placeholder="Filter selected columns..." @input="${e=>this._filterSelectedColumns(e)}" />
                                <div class="btn-list-container">
                                ${this._visibleSelectedColumns.map(e=>j`<button 
                                            draggable="true"
                                            @dragstart="${t=>this._handleDragStart(t,e.id)}"
                                            @dragover="${t=>this._handleDragOver(t,e.id)}"
                                            @dragleave="${()=>this._handleDragLeave(e.id)}"
                                            @drop="${t=>this._handleDrop(t,e.id)}"
                                            @dragend="${this._handleDragEnd}"
                                            @click="${()=>this._handleColumnDeselected(e.id)}" 
                                            class="column-btn selected-column-btn ${this._draggedColumnId===e.id?`dragging`:``} ${this._dragOverColumnId===e.id?`drag-over`:``}"
                                         >${e.title}</button>`)}
                                </div>
                            </div>
                            <div class="available-columns-col">
                                <h4>Available</h4>
                                <input type="text" placeholder="Filter available columns..." @input="${e=>this._filterAvailableColumns(e)}" />
                                <div class="btn-list-container">
                                ${this._visibleAvailableColumns.map(e=>j`<button @click="${()=>this._handleColumnSelected(e.id)}" class="column-btn available-column-btn">${e.title}</button>`)}
                                </div>
                            </div>
                        </div>
                    </div>
                `:``}
            </div>
        `}_filterAvailableColumns(e){let t=e.target;this._visibleAvailableColumns=t==null||t.value==``?this.availableColumns.filter(e=>!this.selectedColumns.some(t=>t.id===e.id)):this.availableColumns.filter(e=>e.title.toLowerCase().includes(t.value.toLowerCase())&&!this.selectedColumns.some(t=>t.id===e.id))}_filterSelectedColumns(e){let t=e.target;this._visibleSelectedColumns=t==null||t.value==``?this.selectedColumns:this.selectedColumns.filter(e=>e.title.toLowerCase().includes(t.value.toLowerCase()))}_toggleCollapsed(){this._collapsed?(this._showContent=!0,requestAnimationFrame(()=>{this._collapsed=!1})):this._collapsed=!0}_handleTransitionEnd(){this._collapsed&&(this._showContent=!1)}_handleColumnSelected(e){let t=this.availableColumns.find(t=>t.id===e);t&&!this.selectedColumns.some(t=>t.id===e)&&(this.selectedColumns=[...this.selectedColumns,t],this._filterSelectedColumns(new Event(`input`)),this._dispatchChanged())}_handleColumnDeselected(e){this.selectedColumns=this.selectedColumns.filter(t=>t.id!==e),this._filterSelectedColumns(new Event(`input`)),this._dispatchChanged()}_handleDragStart(e,t){this._draggedColumnId=t,e.dataTransfer&&(e.dataTransfer.effectAllowed=`move`,e.dataTransfer.setData(`text/plain`,t))}_handleDragOver(e,t){e.preventDefault(),this._draggedColumnId!==t&&(this._dragOverColumnId=t,e.dataTransfer&&(e.dataTransfer.dropEffect=`move`))}_handleDragLeave(e){this._dragOverColumnId===e&&(this._dragOverColumnId=null)}_handleDrop(e,t){e.preventDefault();let n=this._draggedColumnId;if(this._draggedColumnId=null,this._dragOverColumnId=null,n&&n!==t){let e=this.selectedColumns.findIndex(e=>e.id===n),r=this.selectedColumns.findIndex(e=>e.id===t);if(e!==-1&&r!==-1){let t=[...this.selectedColumns],[n]=t.splice(e,1);t.splice(r,0,n),this.selectedColumns=t,this._dispatchChanged()}}}_handleDragEnd(){this._draggedColumnId=null,this._dragOverColumnId=null}_dispatchChanged(){this.dispatchEvent(new CustomEvent(`column-selection-changed`,{detail:{selectedColumns:this.selectedColumns},bubbles:!0,composed:!0}))}};G([H({type:Object})],J.prototype,`availableColumns`,void 0),G([H({type:Object})],J.prototype,`selectedColumns`,void 0),G([U()],J.prototype,`_collapsed`,void 0),G([U()],J.prototype,`_showContent`,void 0),G([U()],J.prototype,`_draggedColumnId`,void 0),G([U()],J.prototype,`_dragOverColumnId`,void 0),G([U()],J.prototype,`_visibleAvailableColumns`,void 0),G([U()],J.prototype,`_visibleSelectedColumns`,void 0),J=G([V(`miqa-monitor-columns`)],J);var Y=class extends B{constructor(...e){super(...e),this.columns=[],this.addString=`Add`,this.advancedFilterString=`Advanced filter`,this.modalityFilterString=`Modality`,this.genderFilterString=`Gender`,this.patientAgeFilterString=`Patient Age`,this.studyDescriptionFilterString=`Study Description`,this.seriesDescriptionFilterString=`Series Description`,this.tagFilterString=`Tag`,this._collapsed=!0,this._showContent=!1}static{this.styles=[W,o`
            .filter-container {
                box-sizing: border-box;
                color: var(--color-text);
                background-color: var(--color-card, #ffffff);
                box-shadow: -2px 0 5px rgba(0, 0, 0, 0.2);
                transition: transform 0.3s ease-in-out;
                border-radius: calc(var(--radius, .75rem) - 2px);
                position: absolute;
                width: 100%;
                z-index: 100;
                top: 0;
                left: 0;
            }
            
            :host {
                display: block;
                position: relative;
                height: 3.5rem;
            }
            
            .filter-header {
                width: 100%;
                display: grid;
                grid-template-columns: auto 1fr auto;
                align-items: center;
                gap: 0.5rem;
                cursor: pointer;
                padding: .75rem 1rem;
                box-sizing: border-box;
                border-radius: calc(var(--radius, .75rem) - 2px);
                border: 1px solid var(--color-border);
            }
            
            .filter-header.expanded {
                border-radius: calc(var(--radius, .75rem) - 2px) calc(var(--radius, .75rem) - 2px) 0 0;
            }
            
            .filter-header:hover {
                background-color: hsl(var(--color-primary-parts) / .5);
            }
            
            .filter-title {
                display: inline-flex;
                gap: .5rem;
                align-items: center;
            }
            
            .toggle-button {
                display: flex;
            }
            
            .toggle-button svg {
                width: 1.8rem;
                fill: currentColor;
                cursor: pointer;
            }
            
            .filter-group {
                width: 100%;
                display: grid;
                align-items: center;
                gap: 0.5rem;
                grid-template-columns: 10rem 1fr auto;
                box-sizing: border-box;
                padding: 0.8rem;
            }
            
            .filter-input {
                background-color: rebeccapurple;
            }
            
            .add-filter-button {
                display: inline-flex;
                gap: .5rem;
                padding: .2rem .5rem;
            }
            
            .add-filter-button svg {
                width: 1rem;
                height: 1rem;
                stroke: currentColor;
            }
        `]}render(){return j`
            <div class="filter-container">
              <div class="filter-header ${this._collapsed?``:`expanded`}" @click="${this._toggleCollapsed}">
                <div class="filter-title">
                  <svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="lucide lucide-filter h-4 w-4 text-muted-foreground"><polygon points="22 3 2 3 10 12.46 10 19 14 21 14 12.46 22 3"></polygon></svg>
                  <span class="semibold text-sm">Filter</span>
                </div>
                <div class="selected-filter-summary"></div>
                <div class="toggle-button" >${this._collapsed?ke:Oe}</div>
              </div>
              <div class="filter-content ${this._collapsed?`collapsed`:``}" @transitionend="${this._handleTransitionEnd}">
                ${this._showContent?j`
                  <div class="filter-group">
                    <div class="filter-label">${this.advancedFilterString}</div>
                    <div class="filter-input">Some content</div>
                    <button class="add-filter-button" @click=${this._handleAddAdvancedFilterClicked}>
                      ${q} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.modalityFilterString}</div>
                    <div class="filter-input"></div>
                    <div></div>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.genderFilterString}</div>
                    <div class="filter-input"></div>
                    <div></div>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.patientAgeFilterString}</div>
                    <div class="filter-input"></div>
                    <div></div>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.studyDescriptionFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddStudyDescriptionFilterClicked}>
                      ${q} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.seriesDescriptionFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddSeriesDescriptionFilterClicked}>
                      ${q} ${this.addString}
                    </button>
                  </div>
                  <div class="filter-group">
                    <div class="filter-label">${this.tagFilterString}</div>
                    <div class="filter-input"></div>
                    <button class="add-filter-button" @click=${this._handleAddTagFilterClicked}>
                      ${q} ${this.addString}
                    </button>
                  </div>
                `:``}
              </div>
            </div>
        `}_handleTransitionEnd(){this._collapsed&&(this._showContent=!1)}_toggleCollapsed(){this._collapsed?(this._showContent=!0,requestAnimationFrame(()=>{this._collapsed=!1})):(this._collapsed=!0,this._showContent=!1)}_handleAddAdvancedFilterClicked(){console.log(`Add advanced filter clicked`)}_handleAddStudyDescriptionFilterClicked(){console.log(`Add study description filter clicked`)}_handleAddSeriesDescriptionFilterClicked(){console.log(`Add series description filter clicked`)}_handleAddTagFilterClicked(){console.log(`Add tag filter clicked`)}};G([H({type:Object})],Y.prototype,`columns`,void 0),G([H({type:String})],Y.prototype,`addString`,void 0),G([H({type:String})],Y.prototype,`advancedFilterString`,void 0),G([H({type:String})],Y.prototype,`modalityFilterString`,void 0),G([H({type:String})],Y.prototype,`genderFilterString`,void 0),G([H({type:String})],Y.prototype,`patientAgeFilterString`,void 0),G([H({type:String})],Y.prototype,`studyDescriptionFilterString`,void 0),G([H({type:String})],Y.prototype,`seriesDescriptionFilterString`,void 0),G([H({type:String})],Y.prototype,`tagFilterString`,void 0),G([U()],Y.prototype,`_collapsed`,void 0),G([U()],Y.prototype,`_showContent`,void 0),Y=G([V(`miqa-monitor-filter`)],Y);var je={ATTRIBUTE:1,CHILD:2,PROPERTY:3,BOOLEAN_ATTRIBUTE:4,EVENT:5,ELEMENT:6},Me=e=>(...t)=>({_$litDirective$:e,values:t}),Ne=class{constructor(e){}get _$AU(){return this._$AM._$AU}_$AT(e,t,n){this._$Ct=e,this._$AM=t,this._$Ci=n}_$AS(e,t){return this.update(e,t)}update(e,t){return this.render(...t)}},{I:Pe}=Se,Fe=e=>e,Ie=()=>document.createComment(``),X=(e,t,n)=>{let r=e._$AA.parentNode,i=t===void 0?e._$AB:t._$AA;if(n===void 0)n=new Pe(r.insertBefore(Ie(),i),r.insertBefore(Ie(),i),e,e.options);else{let t=n._$AB.nextSibling,a=n._$AM,o=a!==e;if(o){let t;n._$AQ?.(e),n._$AM=e,n._$AP!==void 0&&(t=e._$AU)!==a._$AU&&n._$AP(t)}if(t!==i||o){let e=n._$AA;for(;e!==t;){let t=Fe(e).nextSibling;Fe(r).insertBefore(e,i),e=t}}}return n},Z=(e,t,n=e)=>(e._$AI(t,n),e),Le={},Re=(e,t=Le)=>e._$AH=t,ze=e=>e._$AH,Q=e=>{e._$AR(),e._$AA.remove()},Be=(e,t,n)=>{let r=new Map;for(let i=t;i<=n;i++)r.set(e[i],i);return r},Ve=Me(class extends Ne{constructor(e){if(super(e),e.type!==je.CHILD)throw Error(`repeat() can only be used in text expressions`)}dt(e,t,n){let r;n===void 0?n=t:t!==void 0&&(r=t);let i=[],a=[],o=0;for(let t of e)i[o]=r?r(t,o):o,a[o]=n(t,o),o++;return{values:a,keys:i}}render(e,t,n){return this.dt(e,t,n).values}update(e,[t,n,r]){let i=ze(e),{values:a,keys:o}=this.dt(t,n,r);if(!Array.isArray(i))return this.ut=o,a;let s=this.ut??=[],c=[],l,u,d=0,f=i.length-1,p=0,m=a.length-1;for(;d<=f&&p<=m;)if(i[d]===null)d++;else if(i[f]===null)f--;else if(s[d]===o[p])c[p]=Z(i[d],a[p]),d++,p++;else if(s[f]===o[m])c[m]=Z(i[f],a[m]),f--,m--;else if(s[d]===o[m])c[m]=Z(i[d],a[m]),X(e,c[m+1],i[d]),d++,m--;else if(s[f]===o[p])c[p]=Z(i[f],a[p]),X(e,i[d],i[f]),f--,p++;else if(l===void 0&&(l=Be(o,p,m),u=Be(s,d,f)),l.has(s[d]))if(l.has(s[f])){let t=u.get(o[p]),n=t===void 0?null:i[t];if(n===null){let t=X(e,i[d]);Z(t,a[p]),c[p]=t}else c[p]=Z(n,a[p]),X(e,i[d],n),i[t]=null;p++}else Q(i[f]),f--;else Q(i[d]),d++;for(;p<=m;){let t=X(e,c[m+1]);Z(t,a[p]),c[p++]=t}for(;d<=f;){let e=i[d++];e!==null&&Q(e)}return this.ut=o,Re(e,c),M}}),$=class extends B{constructor(...e){super(...e),this.selectedColumns=[],this.tableData={columns:[]},this.noDataAvailableString=`No data available`,this._rows=[]}static{this.styles=[W,o`
          .table-container {
              overflow: auto;
          }  
          table {
              text-indent: 0;
              border-collapse: collapse;
              border-color: inherit;
              font-size: var(--mires-font-size-small, .875rem);
              line-height: var(--mires-line-height-small, 1.25rem);
          }
          thead {
              background-color: var(--color-background-darker);
          }  
          thead tr th {
            padding: .75rem 1rem;
          }
        `]}willUpdate(e){e.has(`tableData`)&&this._preCalculateRows()}_preCalculateRows(){if(this.tableData=this.tableData==null?{columns:[]}:this.tableData,this.tableData.columns.length===0){this._rows=[];return}let e=this.tableData.columns[0].values.length,t=this.tableData.columns.length,n=Array(e);for(let r=0;r<e;r++){let e=Array(t);for(let n=0;n<t;n++)e[n]=this.tableData.columns[n].values[r];n[r]=e}this._rows=n}render(){return this.selectedColumns=this.selectedColumns==null?[]:this.selectedColumns,j`
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  ${this.tableData.columns.length===0?this.selectedColumns.length===0?j`<th></th>`:this.selectedColumns.map(e=>j`<th>${e.title}</th>`):this.tableData.columns.map(e=>j`<th>${e.header}</th>`)}
                </tr>
              </thead>
              <tbody>
                ${this._mapTableDataToRows()}
              </tbody>
            </table>
          </div>
        `}_mapTableDataToRows(){return this._rows.length===0?j`<tr><td colspan="${this.selectedColumns.length}">${this.noDataAvailableString}</td></tr>`:j`
            ${Ve(this._rows,(e,t)=>t,e=>j`
                    <tr>
                        ${e.map(e=>j`<td>${e}</td>`)}
                    </tr>
                `)}
        `}};G([H({type:Object})],$.prototype,`selectedColumns`,void 0),G([H({type:Object})],$.prototype,`tableData`,void 0),G([H({type:String})],$.prototype,`noDataAvailableString`,void 0),G([U()],$.prototype,`_rows`,void 0),$=G([V(`miqa-monitor-table`)],$);