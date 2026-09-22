/**
 * 画面の挙動を確かめる。ここだけブラウザが要る。
 *
 *     make test-browser
 *
 * 生成物を置いたまま http で配って、ヘッドレス Chrome で叩く。file:// でも
 * 大半は動くが、フォントの読み込みは同一オリジンでないと確かめられない。
 *
 * 並んでいるのはどれも実際に踏んだもの。とくに「絞り込んだ状態で再読み込み」は
 * 直したつもりで直っていなかったことが二度あるので、機械で見るようにした。
 */
import { afterAll, beforeAll, describe, expect, test } from "bun:test";
import { existsSync, readdirSync } from "node:fs";
import { homedir } from "node:os";
import puppeteer, { type Browser, type Page } from "puppeteer-core";

const DOCS = new URL("../../docs/", import.meta.url).pathname;
const PORT = 18771;
const ROOT = `http://127.0.0.1:${PORT}`;

/** Chrome を探す。見つからなければ丸ごと飛ばす。 */
function findChrome(): string | null {
  if (process.env.CHROME && existsSync(process.env.CHROME)) return process.env.CHROME;
  const cache = `${homedir()}/.cache/puppeteer/chrome`;
  if (existsSync(cache)) {
    for (const d of readdirSync(cache)) {
      const p = `${cache}/${d}/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing`;
      if (existsSync(p)) return p;
    }
  }
  const app = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
  return existsSync(app) ? app : null;
}

const CHROME = findChrome();
const READY = CHROME !== null && existsSync(`${DOCS}kstrange/index.html`);
let browser: Browser;
let server: ReturnType<typeof Bun.spawn>;

beforeAll(async () => {
  if (!READY) return;
  server = Bun.spawn(["python3", "-m", "http.server", "--bind", "127.0.0.1",
                      "--directory", DOCS, String(PORT)],
                     { stdout: "ignore", stderr: "ignore" });
  await Bun.sleep(700);
  browser = await puppeteer.launch({ executablePath: CHROME!, headless: true });
}, 60_000);   // Chrome の起動は既定の 5 秒に収まらない
afterAll(async () => { await browser?.close(); server?.kill(); }, 30_000);

/** 画面の状態。位置は画素ではなく「上に来ている行」で見る。 */
const snapshot = () => ({
  q: (document.getElementById("q") as HTMLInputElement).value,
  chip: [...document.querySelectorAll(".chip.on")].map((e) => e.textContent?.trim()).join(),
  sort: [...document.querySelectorAll("[data-sort].on")].map((e) => e.textContent?.trim()).join(),
  shown: [...document.querySelectorAll("#tb tr")]
    .filter((r) => (r as HTMLElement).style.display !== "none").length,
  topRow: (() => {
    for (const r of document.querySelectorAll("#tb tr")) {
      if ((r as HTMLElement).style.display === "none") continue;
      if (r.getBoundingClientRect().bottom > 0)
        return (r.querySelector(".cp") as HTMLElement)?.textContent;
    }
    return null;
  })(),
});

async function open(path: string, w = 1400, h = 900, scheme: "light" | "dark" = "light") {
  const p = await browser.newPage();
  await p.setViewport({ width: w, height: h });
  await p.emulateMediaFeatures([{ name: "prefers-color-scheme", value: scheme }]);
  await p.goto(ROOT + path, { waitUntil: "load" });
  await Bun.sleep(600);
  return p;
}
const clickChip = (p: Page, cat: string) =>
  p.evaluate((c) => (document.querySelector(`.chip[data-cat="${c}"]`) as HTMLElement).click(), cat);

describe.if(READY)("kStrange の一覧", () => {
  test("絞り込み・並べ替え・検索が効く", async () => {
    const p = await open("/kstrange/");
    expect((await p.evaluate(snapshot)).shown).toBe(828);
    await clickChip(p, "S");
    await Bun.sleep(300);
    expect((await p.evaluate(snapshot)).shown).toBe(26);
    await clickChip(p, "");
    await p.type("#q", "難読姓氏");
    await Bun.sleep(300);
    expect((await p.evaluate(snapshot)).shown).toBe(1);
    await p.close();
  });

  test("再読み込みで見た目が戻る", async () => {
    const p = await open("/kstrange/");
    await clickChip(p, "I");
    await p.evaluate(() => (document.querySelector('[data-sort="strokes"]') as HTMLElement).click());
    await Bun.sleep(300);
    await p.evaluate(() => scrollTo(0, 6000));
    await Bun.sleep(700);
    const before = await p.evaluate(snapshot);
    await p.reload({ waitUntil: "load" });
    await Bun.sleep(2500);
    expect(await p.evaluate(snapshot)).toEqual(before);
    await p.close();
  });

  test("別のチップは先頭から、戻ると元の場所", async () => {
    const p = await open("/kstrange/");
    await p.evaluate(() => scrollTo(0, 5000));
    await Bun.sleep(700);
    const atAll = await p.evaluate(snapshot);
    await clickChip(p, "I");
    await Bun.sleep(1800);
    expect((await p.evaluate(snapshot)).topRow).toBe(
      await p.evaluate(() => (document.querySelector("#tb tr:not([style*='display: none']) .cp") as HTMLElement).textContent));
    await clickChip(p, "");
    await Bun.sleep(2200);
    expect((await p.evaluate(snapshot)).topRow).toBe(atAll.topRow);
    await p.close();
  });

  test("しばらく経つと読みかけの位置は捨てる", async () => {
    const p = await open("/kstrange/");
    await p.evaluate(() => scrollTo(0, 5000));
    await Bun.sleep(700);
    await p.evaluate(() => {
      const v = JSON.parse(sessionStorage.getItem("kanji:kstrange:view")!);
      v.t = Date.now() - 31 * 60 * 1000;
      sessionStorage.setItem("kanji:kstrange:view", JSON.stringify(v));
      (Storage.prototype as { setItem: unknown }).setItem = () => {};  // 離脱時の保存を止める
    });
    await p.reload({ waitUntil: "load" });
    await Bun.sleep(2200);
    expect(await p.evaluate(() => Math.round(scrollY))).toBe(0);
    await p.close();
  });
});

describe.if(READY)("見た目", () => {
  test.each([1400, 950, 899, 600, 390])("%i px で横に溢れない", async (w) => {
    const p = await open("/kstrange/", w, 900);
    const { doc, win } = await p.evaluate(() => ({
      doc: document.documentElement.scrollWidth, win: innerWidth }));
    expect(doc).toBeLessThanOrEqual(win + 1);
    await p.close();
  });

  test("900px を境に表とカードが入れ替わる", async () => {
    const wide = await open("/kstrange/", 950, 900);
    expect(await wide.evaluate(() => getComputedStyle(document.querySelector("#tb tr")!).display))
      .toBe("table-row");
    await wide.close();
    const narrow = await open("/kstrange/", 899, 900);
    expect(await narrow.evaluate(() => getComputedStyle(document.querySelector("#tb tr")!).display))
      .toBe("grid");
    // 狭いときは出典を畳む
    expect(await narrow.evaluate(() => (document.querySelector("details.dt") as HTMLDetailsElement).open))
      .toBe(false);
    await narrow.close();
  });

  test("スクロールしてもフィルタチップが残る", async () => {
    const p = await open("/kstrange/");
    await p.evaluate(() => scrollTo(0, 4000));
    await Bun.sleep(600);
    expect(await p.evaluate(() => {
      const b = document.querySelector(".chips")!.getBoundingClientRect();
      return b.top >= 0 && b.bottom < innerHeight;
    })).toBe(true);
    await p.close();
  });

  test("暗い配色で字形が沈まない", async () => {
    const p = await open("/kstrange/", 1400, 900, "dark");
    expect(await p.evaluate(() =>
      getComputedStyle(document.querySelector("td.g > img")!).filter)).toBe("invert(1)");
    await p.close();
  });
});

describe.if(READY)("UK-source", () => {
  test("提出文書のフォントが読めている", async () => {
    const p = await browser.newPage();
    const failed: string[] = [];
    p.on("response", (r) => { if (r.status() >= 400 && !r.url().endsWith("favicon.ico")) failed.push(r.url()); });
    await p.setViewport({ width: 1400, height: 900 });
    await p.goto(`${ROOT}/uk/`, { waitUntil: "networkidle2" });
    await Bun.sleep(1200);
    const fonts = await p.evaluate(() =>
      [...(document as unknown as { fonts: Iterable<{ family: string; status: string }> }).fonts]
        .map((f) => `${f.family}:${f.status}`));
    expect(fonts).toEqual(expect.arrayContaining(
      ["uk2015:loaded", "uk2017:loaded", "uk2021:loaded"]));
    expect(failed).toEqual([]);
    await p.close();
  });
});

describe.if(READY)("コレクションをまたぐ", () => {
  test("絞り込んだまま別の一覧へ行っても、全件が出る", async () => {
    // 覚える場所を 1 つの鍵で共有していたため、kStrange でカテゴリ S を
    // 選んだ状態が UK-source でも復元され、そのチップが無いので 1 件も
    // 出なくなっていた。
    const p = await open("/kstrange/");
    await clickChip(p, "S");
    await Bun.sleep(400);
    expect((await p.evaluate(snapshot)).shown).toBe(26);
    await p.goto(`${ROOT}/uk/`, { waitUntil: "load" });
    await Bun.sleep(1500);
    const uk = await p.evaluate(snapshot);
    expect(uk.shown).toBe(3409);
    expect(uk.chip).toStartWith("すべて");
    // 戻れば kStrange 側の絞り込みは残っている
    await p.goto(`${ROOT}/kstrange/`, { waitUntil: "load" });
    await Bun.sleep(1500);
    expect((await p.evaluate(snapshot)).shown).toBe(26);
    await p.close();
  });

  test("知らない分類が残っていても 0 件にしない", async () => {
    const p = await open("/kstrange/");
    await p.evaluate(() => {
      const k = "kanji:kstrange:view";
      const v = JSON.parse(sessionStorage.getItem(k) || "{}");
      v.cat = "存在しない分類";
      sessionStorage.setItem(k, JSON.stringify(v));
    });
    await p.reload({ waitUntil: "load" });
    await Bun.sleep(1200);
    expect((await p.evaluate(snapshot)).shown).toBe(828);
    await p.close();
  });
});

describe.if(READY)("1 字ずつ引く", () => {
  /** 今出ている 1 字のコードポイント。 */
  const only = () => {
    const r = [...document.querySelectorAll("#tb tr")]
      .filter((x) => (x as HTMLElement).style.display !== "none");
    return { n: r.length, cp: (r[0]?.querySelector(".cp") as HTMLElement)?.textContent ?? null,
             pos: document.getElementById("pos")?.textContent ?? "" };
  };
  const press = (p: Page, id: string) =>
    p.evaluate((i) => (document.getElementById(i) as HTMLElement).click(), id);

  test("押すたびに 1 字ずつ出て、同じ字は戻ってこない", async () => {
    const p = await open("/kstrange/");
    await press(p, "lucky");
    await Bun.sleep(300);
    const first = await p.evaluate(only);
    expect(first.n).toBe(1);
    expect(first.pos).toBe("1 字目 / 828");

    const seen = [first.cp];
    for (let i = 0; i < 12; i++) {
      await press(p, "nx");
      await Bun.sleep(80);
      const s = await p.evaluate(only);
      expect(s.n).toBe(1);
      expect(s.pos).toBe(`${i + 2} 字目 / 828`);
      seen.push(s.cp);
    }
    // 山札を配り切るまで重複しない
    expect(new Set(seen).size).toBe(13);
    await p.close();
  });

  test("前の字に戻れる", async () => {
    const p = await open("/kstrange/");
    await press(p, "lucky");
    await Bun.sleep(300);
    const a = (await p.evaluate(only)).cp;
    await press(p, "nx");
    await Bun.sleep(80);
    const b = (await p.evaluate(only)).cp;
    expect(b).not.toBe(a);
    await press(p, "prev");
    await Bun.sleep(80);
    expect((await p.evaluate(only)).cp).toBe(a);
    await p.close();
  });

  test("キーボードで送れる", async () => {
    const p = await open("/kstrange/");
    await press(p, "lucky");
    await Bun.sleep(300);
    const a = (await p.evaluate(only)).cp;
    await p.keyboard.press("ArrowRight");
    await Bun.sleep(120);
    const b = (await p.evaluate(only)).cp;
    expect(b).not.toBe(a);
    await p.keyboard.press("ArrowLeft");
    await Bun.sleep(120);
    expect((await p.evaluate(only)).cp).toBe(a);
    // Esc でやめると全件に戻る
    await p.keyboard.press("Escape");
    await Bun.sleep(300);
    expect((await p.evaluate(snapshot)).shown).toBe(828);
    await p.close();
  });

  test("絞り込んだ中からだけ出す", async () => {
    const p = await open("/kstrange/");
    await clickChip(p, "S");
    await Bun.sleep(300);
    await press(p, "lucky");
    await Bun.sleep(300);
    expect((await p.evaluate(only)).pos).toBe("1 字目 / 26");
    // 出ている字が本当に S の字か
    const ok = await p.evaluate(() => {
      const r = [...document.querySelectorAll("#tb tr")]
        .find((x) => (x as HTMLElement).style.display !== "none") as HTMLElement;
      return (r.dataset.cats || "").split(" ").includes("S");
    });
    expect(ok).toBe(true);
    await p.close();
  });

  test("引いている途中で再読み込みしても同じ字", async () => {
    const p = await open("/kstrange/");
    await press(p, "lucky");
    await Bun.sleep(300);
    await press(p, "nx");
    await press(p, "nx");
    await Bun.sleep(200);
    const before = await p.evaluate(only);
    await p.reload({ waitUntil: "load" });
    await Bun.sleep(1200);
    expect(await p.evaluate(only)).toEqual(before);
    await p.close();
  });

  test("やめると元の一覧に戻る", async () => {
    const p = await open("/kstrange/");
    await press(p, "lucky");
    await Bun.sleep(300);
    expect((await p.evaluate(only)).n).toBe(1);
    await press(p, "quit");
    await Bun.sleep(300);
    const s = await p.evaluate(snapshot);
    expect(s.shown).toBe(828);
    expect(s.sort).toBe("コードポイント順");
    await p.close();
  });

  test("どの一覧にもボタンがある", async () => {
    for (const [path, total] of [["/uk/", 3409], ["/u-source/", 885],
                                 ["/spoofing/", 353]] as const) {
      const p = await open(path);
      await press(p, "lucky");
      await Bun.sleep(400);
      const s = await p.evaluate(only);
      expect(s.n).toBe(1);
      expect(s.pos).toBe(`1 字目 / ${total}`);
      await p.close();
    }
  }, 30_000);
});
