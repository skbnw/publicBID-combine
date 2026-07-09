import fs from "node:fs";
import path from "node:path";
import { marked } from "file:///C:/Users/user/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/marked/lib/marked.esm.js";

const root = path.resolve(import.meta.dirname, "..");
const source = path.join(root, "output", "article_ministry_consulting_share.md");
const target = path.join(root, "output", "article_ministry_consulting_share.html");
const markdown = fs.readFileSync(source, "utf8");
const body = marked.parse(markdown);
const title = "官公庁コンサル市場、12年で落札額11倍";
const css = `
body{margin:0;background:#f4f6fa;color:#182033;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans JP",sans-serif;line-height:1.9}
article{max-width:880px;margin:0 auto;background:#fff;padding:50px 70px;box-shadow:0 2px 20px #17203315}
h1{font-size:34px;line-height:1.35;margin:0 0 28px}h2{margin-top:48px;border-left:5px solid #2563eb;padding-left:14px;line-height:1.45}
p{margin:16px 0}li{margin:7px 0}strong{color:#102a56}a{color:#155eef}.table-wrap{overflow:auto}
table{border-collapse:collapse;width:100%;font-size:14px;margin:25px 0;display:block;overflow:auto;white-space:nowrap}
th,td{padding:9px 11px;border-bottom:1px solid #dde3ec;text-align:right}th:nth-child(2),th:nth-child(3),td:nth-child(2),td:nth-child(3){text-align:left}th{background:#eef3fb}
blockquote{border-left:4px solid #9ab7ee;margin:20px 0;padding:4px 18px;color:#475467;background:#f7f9fc}
@media(max-width:720px){article{padding:26px 18px}h1{font-size:27px}h2{font-size:21px}}
`;
const document = `<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>${title}</title><style>${css}</style></head><body><article>${body}</article></body></html>`;
fs.writeFileSync(target, document, "utf8");
console.log(target);
