/**
 * 配信している実物を、Cloudflare Access 越しに確かめる。
 *
 *     make test-access
 *
 * make test / make test-browser は手元の生成物を見るだけなので、ここでしか
 * 分からないことがある。
 *
 *   * 外から読めてしまっていないか (いちばん大事。生成物には公開したくない
 *     ものが混ざっているので、認証が外れたら気付けないと困る)
 *   * 圧縮が末端まで効いているか (オリジンで gzip しても、経路のどこかで
 *     解かれたら意味が無い)
 *   * Cache-Control がトンネルを越えて残っているか
 *   * 手元のものが本当に届いているか
 *
 * 宛先も資格情報も環境で渡す。リポジトリにホスト名を書かない。
 *
 *   KANJI_URL                 https://<ホスト>  (末尾のスラッシュ無し)
 *   CF_ACCESS_CLIENT_ID       Access のサービストークン
 *   CF_ACCESS_CLIENT_SECRET
 *
 * KANJI_URL だけあれば「外から読めない」ことは確かめられる (資格情報が
 * 要らないのが点検の要点)。残りはサービストークンを渡したときだけ動く。
 */
import { describe, expect, test } from "bun:test";
import { createHash } from "node:crypto";
import { existsSync, readFileSync } from "node:fs";

const SITE = (process.env.KANJI_URL || "").replace(/\/$/, "");
const ID = process.env.CF_ACCESS_CLIENT_ID || "";
const SECRET = process.env.CF_ACCESS_CLIENT_SECRET || "";
const LIVE = SITE !== "";
const AUTHED = LIVE && ID !== "" && SECRET !== "";

const DOCS = new URL("../../docs/", import.meta.url).pathname;
// worktree には生成物が付いてこない。手元に無ければ突き合わせは飛ばす
const BUILT = existsSync(`${DOCS}kstrange/index.html`);
/** 一覧のページ。件数は build_html が書くので、ここでは持たない。 */
const PAGES = ["/", "/lucky/", "/kstrange/", "/uk/", "/u-source/", "/spoofing/"];

if (!LIVE) console.log("KANJI_URL が無いので、配信の点検は飛ばす");
else if (!AUTHED) console.log("サービストークンが無いので、認証の要る点検は飛ばす");

type Res = { code: number; size: number; headers: Record<string, string>; body: string };

/** curl で引く。fetch は Content-Encoding を伏せてしまうので使わない。 */
async function get(path: string, o: { auth?: boolean; body?: boolean; raw?: boolean;
                                      since?: string } = {}): Promise<Res> {
  const args = ["curl", "-sS", "--max-time", "60", "-D", "/dev/stderr"];
  // 大きさを測るときは curl に展開させない (圧縮後の byte 数が知りたい)。
  // 中身を読むときは --compressed で展開させる。生のまま読むと gzip の
  // バイト列を UTF-8 として解釈してしまい、md5 が合わなくなる
  if (o.raw) args.push("-H", "Accept-Encoding: identity");
  else if (o.body) args.push("--compressed");
  else args.push("-H", "Accept-Encoding: gzip");
  if (o.auth) args.push("-H", `CF-Access-Client-Id: ${ID}`,
                        "-H", `CF-Access-Client-Secret: ${SECRET}`);
  if (o.since) args.push("-H", `If-Modified-Since: ${o.since}`);
  if (!o.body) args.push("-o", "/dev/null", "-w", "%{size_download}");
  args.push(SITE + path);

  const p = Bun.spawn(args, { stdout: "pipe", stderr: "pipe" });
  const [out, err] = await Promise.all([
    new Response(p.stdout).text(), new Response(p.stderr).text()]);
  const headers: Record<string, string> = {};
  let code = 0;
  for (const line of err.split("\n").map((l) => l.replace(/\r$/, ""))) {
    const m = /^HTTP\/[\d.]+ (\d+)/.exec(line);
    if (m) { code = Number(m[1]); continue; }
    const i = line.indexOf(":");
    if (i > 0) headers[line.slice(0, i).toLowerCase()] = line.slice(i + 1).trim();
  }
  return { code, headers, body: o.body ? out : "",
           size: o.body ? Buffer.byteLength(out) : Number(out || 0) };
}

describe.if(LIVE)("外から読めないこと", () => {
  // 資格情報を渡さない。ここが通ってしまったら、生成物が世界に見えている
  test.each(PAGES)("%s は認証を求める", async (path) => {
    const r = await get(path);
    expect(r.code).toBe(302);
    expect(r.headers["location"]).toInclude("cloudflareaccess.com");
  }, 60_000);

  test("字形の SVG も守られている", async () => {
    // ページだけ守って中身が素通り、という穴が開いていないか
    const r = await get("/glyphs/u3b35.svg");
    expect(r.code).toBe(302);
  }, 60_000);

  test("中身が 1 文字も漏れていない", async () => {
    const r = await get("/kstrange/", { body: true });
    expect(r.body).not.toInclude('id="tb"');
    expect(r.body).not.toInclude("kStrange");
  }, 60_000);

  test("でたらめなサービストークンでは通らない", async () => {
    const args = ["curl", "-sS", "-o", "/dev/null", "-w", "%{http_code}",
                  "--max-time", "60",
                  "-H", "CF-Access-Client-Id: 0000000000000000000000000000000.access",
                  "-H", "CF-Access-Client-Secret: " + "0".repeat(64),
                  SITE + "/kstrange/"];
    const p = Bun.spawn(args, { stdout: "pipe" });
    expect(Number(await new Response(p.stdout).text())).not.toBe(200);
  }, 60_000);
});

describe.if(AUTHED)("サービストークンで通ること", () => {
  test.each(PAGES)("%s が返る", async (path) => {
    const r = await get(path, { auth: true });
    expect(r.code).toBe(200);
    expect(r.size).toBeGreaterThan(0);
  }, 60_000);

  test("圧縮が末端まで効いている", async () => {
    // オリジンで gzip しても、経路のどこかで解かれたら意味が無い。
    // 生の 8.5 MB が流れていたのを直したので、そこへ戻っていないかを見る
    const gz = await get("/uk/", { auth: true });
    expect(gz.headers["content-encoding"]).toBe("gzip");
    expect(gz.size).toBeLessThan(2_000_000);

    const raw = await get("/uk/", { auth: true, raw: true });
    expect(raw.size).toBeGreaterThan(gz.size * 4);   // 実測 12 倍
  }, 120_000);

  test("Cache-Control がトンネルを越えて残っている", async () => {
    // HTML を持たれると、更新したのに古いページが出る。
    // 字形は名前で中身が決まるので、逆に長く持たせたい
    expect((await get("/kstrange/", { auth: true })).headers["cache-control"])
      .toInclude("no-cache");
    expect((await get("/glyphs/u3b35.svg", { auth: true })).headers["cache-control"])
      .toInclude("immutable");
  }, 60_000);

  test("変わっていなければ 304 で済む", async () => {
    const first = await get("/kstrange/", { auth: true });
    const again = await get("/kstrange/",
                            { auth: true, since: first.headers["last-modified"] });
    expect(again.code).toBe(304);
    expect(again.size).toBe(0);
  }, 60_000);

  test.if(BUILT)("手元のものが本当に届いている", async () => {
    // rsync の抜けや、古い生成物が残っているのに気付けるようにする
    const md5 = (s: string | Buffer) => createHash("md5").update(s).digest("hex");
    for (const slug of ["kstrange", "spoofing"]) {
      const here = readFileSync(`${DOCS}${slug}/index.html`);
      const there = await get(`/${slug}/`, { auth: true, body: true });
      expect(md5(there.body)).toBe(md5(here.toString()));
    }
  }, 120_000);
});
