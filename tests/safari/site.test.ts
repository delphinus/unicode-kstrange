/**
 * Safari で画面の挙動を確かめる。指定したときだけ動かす。
 *
 *     make test-safari
 *
 * ヘッドレスの WebKit (Playwright) と本物の Safari は挙動が違うので、Safari は
 * safaridriver で動かす。ただしヘッドレスにできず、流している間は Safari の
 * ウィンドウが前面に出て操作される。そのため make test-browser には混ぜない。
 *
 * 事前に 1 回だけ、Safari → 設定 → デベロッパ →「リモートオートメーションを許可」を
 * オンにしておく (デベロッパのタブは、設定 → 詳細 →「Web 開発者向けの機能を表示」で出る)。
 *
 * puppeteer は Safari を動かせないので、WebDriver を HTTP で直に叩く。
 * safaridriver は同時に 1 セッションしか張れないので、全部のテストで 1 つを使い回す。
 */
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { existsSync } from "node:fs";

const DOCS = new URL("../../docs/", import.meta.url).pathname;
const PORT = 18772;              // make test-browser (18771) と同時に流しても当たらない
const ROOT = `http://127.0.0.1:${PORT}`;
const DPORT = 18773;
const DRIVER = `http://127.0.0.1:${DPORT}`;

const READY = existsSync("/usr/bin/safaridriver") && existsSync(`${DOCS}kstrange/index.html`);
let server: ReturnType<typeof Bun.spawn>;
let driver: ReturnType<typeof Bun.spawn>;
let sid = "";

/** WebDriver の命令を 1 つ送る。エラーは Safari の文言のまま投げる。 */
async function call(method: string, path: string, body?: unknown) {
  const r = await fetch(DRIVER + path, {
    method, headers: { "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body) });
  const j = (await r.json()) as { value: any };
  if (j.value?.error) throw new Error(`${j.value.error}: ${j.value.message}`);
  return j.value;
}
/** ページの中で関数本体を動かす。引数は arguments[0] から。 */
const run = (script: string, ...args: unknown[]) =>
  call("POST", `/session/${sid}/execute/sync`, { script, args });

async function open(path: string, w = 1400, h = 900) {
  await call("POST", `/session/${sid}/window/rect`, { width: w, height: h });
  // 絞り込みや位置は sessionStorage に残って次に開いたときに戻るので、前のテストのぶんを
  // 消す。一覧の上で消しても離れるとき (pagehide) に書き戻されるので、トップに移ってから消す
  await call("POST", `/session/${sid}/url`, { url: ROOT + "/" });
  await run("sessionStorage.clear();");
  await call("POST", `/session/${sid}/url`, { url: ROOT + path });
  await Bun.sleep(1500);
}
/** 人が押すのと同じくクリックする (open = true を代入するのとはやり方が違う)。 */
async function click(css: string) {
  const el = await call("POST", `/session/${sid}/element`, { using: "css selector", value: css });
  await call("POST", `/session/${sid}/element/${Object.values(el)[0]}/click`, {});
}
/** 符号位置の行に id を振って、CSS で指せるようにする。 */
const mark = (cp: string) => run(`
  const r=[...document.querySelectorAll('#tb tr')]
    .find(r=>r.querySelector('.cp')?.textContent.trim()===arguments[0]);
  r.id='t'; return r.getBoundingClientRect().top;`, cp);
/** その行の見比べに並んだ字形の、読み込めた幅。0 なら読み込めていない。 */
const widths = () => run(`
  return [...document.querySelectorAll('#t details.sv .sv1 img')].map(i=>i.naturalWidth);`);

beforeAll(async () => {
  if (!READY) return;
  server = Bun.spawn(["python3", "-m", "http.server", "--bind", "127.0.0.1",
                      "--directory", DOCS, String(PORT)],
                     { stdout: "ignore", stderr: "ignore" });
  driver = Bun.spawn(["/usr/bin/safaridriver", "-p", String(DPORT)],
                     { stdout: "ignore", stderr: "ignore" });
  await Bun.sleep(1000);
  // 設定がオフならここで落ちる。何も言わずに飛ばすと、流したつもりで何も見ていないことになる
  sid = (await call("POST", "/session",
                    { capabilities: { alwaysMatch: { browserName: "safari" } } })).sessionId;
}, 60_000);
afterAll(async () => {
  if (sid) await call("DELETE", `/session/${sid}`).catch(() => {});
  driver?.kill(); server?.kill();
}, 30_000);

describe.if(READY)("国ごとの字形 (Safari)", () => {
  test("検索で絞ってから開くと、字形が読み込まれる", async () => {
    await open("/spoofing/");
    await run(`const q=document.getElementById('q');
               q.value=arguments[0]; q.dispatchEvent(new Event('input'));`, "U+4C17");
    await Bun.sleep(800);
    await mark("U+4C17");
    await click("#t details.sv > summary");
    await Bun.sleep(2500);
    const w = await widths();
    expect(w.length).toBe(3);                    // 日 中 台
    expect(w.every((x: number) => x > 0)).toBe(true);
  });

  test("絞り込まずにスクロールで辿り着いても、狭い画面でも読み込まれる", async () => {
    // 上から 1 画面ずつ送って、途中の行の字形の要求をまとめて飛ばしてから開く
    await open("/spoofing/", 500);
    for (let i = 0; i < 400 && (await mark("U+7361")) > 450; i++) {
      await run("scrollBy(0, innerHeight * 0.8)");
      await Bun.sleep(120);
    }
    await Bun.sleep(1000);
    await click("#t details.sv > summary");
    await Bun.sleep(2500);
    const w = await widths();
    expect(w.length).toBe(3);                    // 日韓 / 中朝 / 台港
    expect(w.every((x: number) => x > 0)).toBe(true);
  });
});
