// Чистая страница под копирование: только тело статьи, без заголовка H1,
// без навигации, шапки, подвала и кнопок. Открыл, Cmd+A, Cmd+C.
// Форматирование (заголовки, жирное, списки, код, цитаты, ссылки) переносится как rich text.
const fs = require('fs');
const path = require('path');
const { marked } = require('marked');
const base = path.resolve(__dirname, '..');

const JOBS = [
  { md: 'jev-engineering.en.md', out: 'jev-engineering.en.paste.html', lang: 'en',
    title: 'Jev + Harness Engineering — body for pasting',
    note: 'Select all and copy. Headings, bold, lists, code and links carry over. The title is not here on purpose: it goes in its own field. Images are omitted, upload them separately.' },
  { md: 'jev-engineering.md', out: 'jev-engineering.paste.html', lang: 'ru',
    title: 'Jev + Harness Engineering — тело статьи для вставки',
    note: 'Выделить всё и скопировать. Заголовки, жирное, списки, код и ссылки переносятся. Заголовка H1 здесь нет специально: он вбивается в отдельное поле. Картинки опущены, их грузить отдельно.' },
];

const CSS = `body{margin:0;background:#fff;color:#111;font:17px/1.65 -apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif}
.note{max-width:860px;margin:0 auto;padding:14px 24px;color:#666;font-size:13px;border-bottom:1px solid #e3e3e3;background:#fafafa}
main{max-width:860px;margin:0 auto;padding:28px 24px 90px}
h2{font-size:27px;line-height:1.25;margin:44px 0 16px}h3{font-size:21px;margin:30px 0 12px}
p{margin:0 0 18px}ul,ol{padding-left:24px;margin:18px 0}li{margin:0 0 10px}
blockquote{margin:22px 0;padding:6px 0 6px 18px;border-left:3px solid #c0c0c0;color:#333}
blockquote p{margin:0 0 8px}
code{font-family:ui-monospace,SFMono-Regular,Consolas,monospace;font-size:.86em;background:#f1f1f1;padding:.1em .3em}
pre{background:#f1f1f1;border:1px solid #e0e0e0;padding:16px;overflow-x:auto;font-size:14px;line-height:1.55;margin:22px 0}
pre code{background:none;padding:0;font-size:1em}
a{color:#0b57d0}hr{border:0;border-top:1px solid #e0e0e0;margin:36px 0}
@media print{.note{display:none}}`;

for (const job of JOBS) {
  const md = fs.readFileSync(path.join(base, job.md), 'utf8');
  const bodyMd = md.replace(/^#\s+.*\r?\n+/, '');            // выкидываем H1
  let html = marked.parse(bodyMd);
  html = html.replace(/<img[^>]*>/g, '');                    // картинки грузятся в редакторе отдельно
  html = html.replace(/href="\.\/([^"]+)"/g,
    (_, rel) => `href="https://github.com/Archive228/jev-harness-engineering/blob/main/${rel}"`);

  const page = `<!doctype html><html lang="${job.lang}"><head><meta charset="utf-8">`
    + `<meta name="viewport" content="width=device-width,initial-scale=1">`
    + `<title>${job.title}</title><style>${CSS}</style></head><body>`
    + `<div class="note">${job.note}</div><main>${html}</main></body></html>`;

  fs.writeFileSync(path.join(base, job.out), page);
  const text = html.replace(/<[^>]+>/g, '');
  console.log(JSON.stringify({ file: job.out, html_bytes: Buffer.byteLength(page), text_chars: text.length }));
}
