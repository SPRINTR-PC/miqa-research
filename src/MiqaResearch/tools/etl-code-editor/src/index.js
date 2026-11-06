// Progressive enhancement for `<textarea data-etl-code-editor>`: swaps it for a CodeMirror 6 editor,
// keeps the textarea (hidden) as the form value, and wires the language <select> and the
// "load from file" input. Works on htmx-swapped content via `mires:etl-editor-init` / htmx:load.
import {EditorState, Compartment, Transaction} from "@codemirror/state";
import {EditorView, keymap, lineNumbers, highlightActiveLine} from "@codemirror/view";
import {defaultKeymap, history, historyKeymap, indentWithTab} from "@codemirror/commands";
import {StreamLanguage, syntaxHighlighting, indentUnit} from "@codemirror/language";
import {classHighlighter, highlightCode} from "@lezer/highlight";
import {python, pythonLanguage} from "@codemirror/lang-python";
import {r} from "@codemirror/legacy-modes/mode/r";
import {json} from "@codemirror/legacy-modes/mode/javascript";

const LANGUAGES = {".py": () => python(), ".r": () => StreamLanguage.define(r), ".json": () => StreamLanguage.define(json)};

const INDENT = "    ";

// Indentation is four spaces. The Tab key already indents by `indentUnit`; this filter additionally
// turns any literal tab that enters the document (typed, pasted, loaded from a file) into four spaces.
const tabsToSpaces = EditorState.transactionFilter.of((tr) => {
  if (!tr.docChanged) return tr;
  let hasTab = false;
  tr.changes.iterChanges((fromA, toA, fromB, toB, inserted) => {
    if (inserted.toString().includes("\t")) hasTab = true;
  });
  if (!hasTab) return tr;
  const changes = [];
  tr.changes.iterChanges((fromA, toA, fromB, toB, inserted) => {
    changes.push({from: fromA, to: toA, insert: inserted.toString().replace(/\t/g, INDENT)});
  });
  const rewritten = tr.startState.changes(changes);
  const toRewritten = tr.changes.invert(tr.startState.doc).compose(rewritten);
  return {
    changes: rewritten,
    selection: tr.newSelection.map(toRewritten, 1),
    effects: tr.effects,
    scrollIntoView: tr.scrollIntoView,
    userEvent: tr.annotation(Transaction.userEvent),
  };
});

function languageExtension(extension) {
  const factory = LANGUAGES[(extension || "").toLowerCase()];
  return factory ? factory() : [];
}

function extensionOf(filename) {
  const dot = filename.lastIndexOf(".");
  return dot < 0 ? "" : filename.slice(dot).toLowerCase();
}

function enhance(textarea) {
  if (textarea.dataset.enhanced) return;
  textarea.dataset.enhanced = "1";
  const form = textarea.closest("form");
  // A textarea with `data-etl-fixed-language` (e.g. ".json" for the config schema) has one language and no
  // dropdown; otherwise the form's language <select> drives it. Each load-from-file input names its textarea.
  const fixedLanguage = textarea.dataset.etlFixedLanguage || "";
  const select = fixedLanguage ? null : form.querySelector("[data-etl-language]");
  const fileInput = form.querySelector(`[data-etl-load-file="${textarea.name}"]`);
  const compartment = new Compartment();
  const view = new EditorView({
    parent: textarea.parentNode,
    state: EditorState.create({
      doc: textarea.value,
      extensions: [
        // An editor attribute, not a manual classList.add: CodeMirror rewrites the root's class on focus.
        EditorView.editorAttributes.of({class: "etl-code-editor"}),
        indentUnit.of(INDENT), EditorState.tabSize.of(4), tabsToSpaces,
        lineNumbers(), highlightActiveLine(), history(),
        keymap.of([...defaultKeymap, ...historyKeymap, indentWithTab]),
        // Class-based (tok-*) so the page CSS themes it for light and dark mode.
        syntaxHighlighting(classHighlighter),
        compartment.of(languageExtension(fixedLanguage || (select && select.value))),
        EditorView.updateListener.of((update) => {
          if (update.docChanged) textarea.value = update.state.doc.toString();
        }),
      ],
    }),
  });
  textarea.style.display = "none";
  // A hidden control with `required` makes the browser refuse to submit ("not focusable"); the server validates.
  textarea.removeAttribute("required");

  // Starter code per language (data-etl-templates). Switching language swaps the skeleton only while
  // the code is empty or still the previous language's untouched skeleton -- never the author's work.
  let templates = {};
  try { templates = JSON.parse(textarea.dataset.etlTemplates || "{}"); } catch (error) { templates = {}; }
  let currentExtension = select ? select.value : "";
  const setLanguage = () => {
    const previous = templates[currentExtension];
    currentExtension = select.value;
    view.dispatch({effects: compartment.reconfigure(languageExtension(currentExtension))});
    const code = view.state.doc.toString();
    const next = templates[currentExtension];
    if (next !== undefined && (code.trim() === "" || code === previous) && code !== next) {
      view.dispatch({changes: {from: 0, to: view.state.doc.length, insert: next}});
    }
  };
  if (select) select.addEventListener("change", setLanguage);

  if (fileInput) {
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      if (!file) return;
      const extension = extensionOf(file.name);
      const known = select
        ? Array.from(select.options).some((option) => option.value === extension)
        : extension === fixedLanguage;
      if (!known) {
        fileInput.value = "";
        alert(fileInput.dataset.unsupportedMessage || "Unsupported file type");
        return;
      }
      if (select) {
        select.value = extension;
        setLanguage();
      }
      const text = await file.text();
      view.dispatch({changes: {from: 0, to: view.state.doc.length, insert: text}});
      fileInput.value = ""; // loaded code is treated exactly like typed code; the file itself isn't submitted
    });
  }
}

// Static code examples in the help popovers: `<pre data-etl-highlight="python|r|json">` is coloured
// with the same tok-* classes (and CSS) as the editor.
const PARSERS = {
  python: () => pythonLanguage.parser,
  r: () => StreamLanguage.define(r).parser,
  json: () => StreamLanguage.define(json).parser,
};

function highlightExample(pre) {
  if (pre.dataset.highlighted) return;
  const makeParser = PARSERS[pre.dataset.etlHighlight];
  if (!makeParser) return;
  pre.dataset.highlighted = "1";
  const code = pre.textContent;
  const fragment = document.createDocumentFragment();
  highlightCode(
    code, makeParser().parse(code), classHighlighter,
    (text, classes) => {
      if (!classes) return fragment.append(text);
      const span = document.createElement("span");
      span.className = classes;
      span.textContent = text;
      fragment.append(span);
    },
    () => fragment.append("\n"),
  );
  pre.replaceChildren(fragment);
}

function init(root) {
  root.querySelectorAll("pre[data-etl-highlight]").forEach(highlightExample);
  root.querySelectorAll("textarea[data-etl-code-editor]").forEach(enhance);
}

// The panel re-runs this script on every htmx swap: enhance what is there now, register listeners once.
init(document);
if (!window.__etlCodeEditorLoaded) {
  window.__etlCodeEditorLoaded = true;
  document.addEventListener("htmx:load", (event) => init(event.target));
}
