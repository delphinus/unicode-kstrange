#!/usr/bin/env python3
"""生成物の中身を確かめる。ブラウザは要らない (標準ライブラリだけ)。

    make test        /  python3 -m unittest discover -s tests

ここに並んでいるのは、どれも実際に踏んだ不具合。直したあとで戻っていないかを
見るためのもので、思い付きの網羅ではない。

cache/ が無いと組み立てられないので、その場合は丸ごと飛ばす。
"""
import html
import json
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

from common import CACHE, DOCS, GLYPHS, toml  # noqa: E402

HAVE_CACHE = (CACHE / "Unihan.zip").exists()


def strip(s):
    """タグを外して地の文にする。"""
    return re.sub(r"<[^>]+>", "", s)


def visible(s):
    """画面に見える文字だけ。

    字形に差し替えた字は <span class="sr"> で見えない形で併記してあるので、
    strip() だけだと「差し替えたのに元の字が残っている」と誤って読めてしまう。
    """
    return strip(re.sub(r'<span class="sr">.*?</span>', "", s, flags=re.S))


def glyph_cell(row):
    """行の字形の欄。<span> が入れ子になるので <td> 単位で取る。

    <span class="ids">(.*?)</span> と非貪欲で取ると、中の <span class="sr">
    の閉じタグで切れてしまい、隠してあるはずの字が残って見える。
    """
    return re.search(r'<td class="g">(.*?)</td>', row, re.S).group(1)


@unittest.skipUnless(HAVE_CACHE, "cache/Unihan.zip が無い (make fetch)")
class PageTest(unittest.TestCase):
    """1 コレクションぶんを組み立てて調べる。Unihan の読み込みが重いので共有する。"""

    slug = "kstrange"
    category = "all"
    _cache = {}

    @classmethod
    def page(cls):
        key = (cls.slug, cls.category)
        if key not in PageTest._cache:
            from build_html import Builder
            PageTest._cache[key] = Builder(cls.category, cls.slug).build()
        return PageTest._cache[key]

    @classmethod
    def setUpClass(cls):
        cls.html = cls.page()
        cls.rows = re.findall(r"<tr data-search=.*?</tr>", cls.html, re.S)

    # -- どのコレクションでも成り立つこと -----------------------------------
    def test_rows_exist(self):
        self.assertGreater(len(self.rows), 10)

    def test_shows_the_radical(self):
        """部首を出す。番号だけでなく字も添える。

        74 (月) と 130 (肉) のように、同じ形に見えて部首だけが違う組がある。
        番号だけでは読み手が引けないので、字のほうも並べる。
        """
        n = sum(1 for r in self.rows if re.search(r"部首 \d+'? .", r))
        self.assertGreater(n / len(self.rows), 0.9, "部首の字が出ていない行が多い")

    def test_definitions_are_translated(self):
        """kDefinition は英語なので、訳を並べて出す。

        この表で唯一「読む」ところが英語のままだと意味を取るのに手間が掛かる。
        """
        from build_html import Builder
        b = Builder(self.category, self.slug)
        miss = b.untranslated_unihan(b.select())
        self.assertEqual(miss, [], f"訳の無い kDefinition が {len(miss)} 件")
        # 原文と訳が両方出ていること
        got = sum(1 for r in self.rows if 'class="df"' in r)
        ja = sum(1 for r in self.rows if 'class="dfja"' in r)
        self.assertEqual(got, ja, "原文だけで訳の無い行がある")

    def test_japanese_form_is_preferred(self):
        """字形は日本の形を既定にする。日本語で読むページなので。

        Unicode は各国で少し違う形を 1 つの符号位置にまとめている (包摂) ので、
        符号位置が同じでも国ごとに形が違う。GlyphWiki の既定は字によって
        どの国か揺れるため、-j があればそちらを使う。
        """
        from common import GLYPHS
        n = 0
        for m in re.finditer(r'<td class="g"><img src="\.\./glyphs/(u[0-9a-f]+)\.svg"',
                             self.html):
            # 既定を使っているなら、日本の形が無い字のはず
            self.assertFalse((GLYPHS / f"{m.group(1)}-j.svg").exists(),
                             f"{m.group(1)} は日本の形があるのに使っていない")
            n += 1
        self.assertGreaterEqual(n, 0)

    def test_source_forms_only_when_they_differ(self):
        """見比べは形が 2 通り以上あるときだけ出す。同じ形なら出す意味が無い。"""
        from build_html import Builder
        b = Builder(self.category, self.slug)
        for cp in b.select()[:400]:
            fs = b.forms(cp)
            self.assertNotEqual(len(fs), 1, f"{cp} が 1 種で出ている")
            if fs:
                # 形ごとにまとまっていること (同じ形が 2 列に割れない)
                paths = [p for p, _ in fs]
                self.assertEqual(len(paths), len(set(paths)), cp)

    def test_lucky_controls(self):
        """1 字ずつ引く操作列。数が多くて上から眺められないのはどの一覧も同じ。"""
        for i in ("lucky", "solo", "nx", "prev", "quit", "pos"):
            self.assertIn(f'id="{i}"', self.html, i)
        # 既定は畳んである (.solo に on が付いて初めて出る)
        self.assertIn('<div id="solo" class="solo">', self.html)

    def test_no_nested_anchors(self):
        """<a> の入れ子。字義の字をリンクにしたときに作りかけた。

        用例は URL があると丸ごと <a> に包まれるので、その中で字形をリンクに
        すると入れ子になる。ブラウザが勝手に切るので見た目では気付けない。
        """
        depth = 0
        for m in re.finditer(r"<a\b|</a>", self.html):
            if m.group(0) == "</a>":
                depth = max(0, depth - 1)
            else:
                self.assertEqual(depth, 0, "<a> が入れ子になっている")
                depth += 1

    def test_glyphs_are_shared_at_site_root(self):
        """字形はコレクションごとではなく docs/glyphs/ に置いて共有する。"""
        for src in re.findall(r'src="([^"]*glyphs/[^"]+)"', self.html):
            self.assertTrue(src.startswith("../glyphs/"), src)

    def test_every_referenced_glyph_exists(self):
        """参照している SVG が実在すること。取り損ねても 404 になるだけで気付けない。"""
        missing = {s for s in re.findall(r'src="\.\./glyphs/([^"]+)"', self.html)
                   if not (GLYPHS / s).exists()}
        self.assertFalse(missing, f"字形が無い: {sorted(missing)[:5]}")

    def test_no_empty_section_heading(self):
        """見出しだけあって中身が空、が出ないこと。

        まだ符号化されていない字の列で、IRG ソース参照と字書索引の見出しが
        決め打ちのまま空で出ていた。
        """
        self.assertNotRegex(self.html, r'<div class="h">[^<]*</div><ul></ul>')

    def test_badges_are_short(self):
        """札が長くなりすぎないこと。

        U+2298F の kStrange は関連字を 31 個並べた 382 文字で、コロン区切りは
        折り返せないため、この 1 つで文書幅が 2,932px になっていた。
        """
        for b in re.findall(r'<span class="cat"[^>]*>(.*?)</span>', self.html):
            self.assertLessEqual(len(strip(b)), 24, b[:40])

    def test_nav_does_not_link_to_unbuilt(self):
        """まだ作っていないコレクションはリンクにしない (404 になる)。"""
        nav = re.search(r'<nav class="nav">(.*?)</nav>', self.html, re.S).group(1)
        for c in toml("collections.toml")["collection"]:
            built = (DOCS / c["slug"] / "meta.json").exists()
            linked = f'href="../{c["slug"]}/"' in nav
            if c["slug"] != self.slug:
                self.assertEqual(linked, built, f'{c["slug"]} のリンク')

    def test_substituted_chars_stay_searchable(self):
        """字形に差し替えた字が、検索とコピーから落ちないこと。

        画像だけにすると data-search からも選択範囲からも字が消える。
        直後に見えない <span class="sr"> を併記してある。
        """
        n = 0
        for m in re.finditer(r'<img class="ig"[^>]*>', self.html):
            n += 1
            self.assertTrue(self.html[m.end():].startswith('<span class="sr">'),
                            "差し替えた字形の後ろに隠し文字が無い")
        self.assertGreater(n, 0)

    def test_search_index_is_lowercased_text(self):
        for r in self.rows[:50]:
            s = re.search(r'data-search="([^"]*)"', r).group(1)
            self.assertNotIn("<", s)
            self.assertEqual(s, s.lower())


class KStrangeTest(PageTest):
    slug, category = "kstrange", "all"

    def test_virtual_positions_are_not_linked(self):
        """字書に実在しない仮想位置には字頭検索のリンクを張らない。

        康熙字典の字頭検索は仮想位置だと「查無資料」になる。
        """
        for m in re.finditer(r"<li>([^<]*仮想位置[^<]*)</li>", self.html):
            self.assertNotIn("kangxizidian", m.group(1))

    def test_definitions_have_japanese(self):
        """字義に日本語訳が付いていること (訳語表が無いと原文だけになる)。"""
        if not (ROOT / "data" / "zi_tools_ja.toml").exists():
            self.skipTest("訳語表を置いていない")
        self.assertGreater(self.html.count('class="ja"'), 300)


class UkTest(PageTest):
    slug, category = "uk", "all"

    def test_glyph_comes_from_submission_font(self):
        """字形は提出文書の添付フォント。私用領域の参照になっている。"""
        self.assertGreater(len(re.findall(r'<span class="uk uk20\d\d">&#x[0-9A-F]{4};',
                                          self.html)), 3000)

    def test_font_files_exist(self):
        if not (DOCS / "fonts").exists():
            self.skipTest("docs/fonts/ がまだ無い (make uk-source)")
        for f in ("uk2015", "uk2017", "uk2021"):
            self.assertTrue((DOCS / "fonts" / f"{f}.ttf").exists(), f)

    def test_every_row_has_evidence_or_says_so(self):
        for r in self.rows[:80]:
            ev = re.search(r'<td class="ev[^"]*">(.*?)</td>', r, re.S).group(1)
            self.assertTrue(strip(ev).strip(), "用例の欄が空")


class USourceTest(PageTest):
    slug, category = "u-source", "all"

    def test_no_font_taken_from_unicode(self):
        """Unicode の字形表からフォントを取り出して使わないこと。

        USourceGlyphs.pdf は「You may not extract, copy, modify, or distribute
        fonts or font data from any Unicode Products」と明記している。
        PDF へのリンクは構わない (むしろ張ってある) が、@font-face で
        持ち込んだら違反。この列で使ってよいフォントは UK の提出文書のぶんだけ。
        """
        for m in re.finditer(r"@font-face\s*\{([^}]*)\}", self.html):
            self.assertRegex(m.group(1), r"uk20\d\d\.ttf", m.group(1)[:80])
        self.assertNotIn("usourceglyphs.ttf", self.html.lower())

    def test_every_row_shows_something(self):
        """字形か構成式のどちらかは必ず出ていること。左端が空の行を作らない。"""
        for r in self.rows:
            g = glyph_cell(r)
            self.assertTrue('class="ids"' in g or 'class="idsc"' in g
                            or "<img" in g or 'class="uk ' in g,
                            f"左端が空: {g[:120]}")

    def test_unrepresentable_part_is_marked(self):
        """UAX #45 が符号位置の無い構成要素に置く ？ を、印だと分かる形で出す。

        素で出すと字形の取得に失敗したように見える (UK-02847 でそう見えた)。
        """
        n = 0
        for r in self.rows:
            g = glyph_cell(r)
            if "？" not in g:
                continue
            n += 1
            self.assertIn('class="qm"', g, f"？ が素で出ている: {g[:150]}")
        self.assertGreater(n, 0, "？ を含む行が 1 つも無い")

    def test_uk_submissions_use_their_own_glyph(self):
        """英国の提出文書に字形があるものは、構成式ではなくその字形を出す。

        UK-02847 は構成式が ⿰⿸尸？殳 で、？ のせいで読めない。提出文書の
        添付フォントに字形 (私用領域 EB42) があるので、そちらを出す。
        """
        r = next(x for x in self.rows if ">UK-02847<" in x)
        g = glyph_cell(r)
        self.assertIn("uk2015", g, g[:200])
        self.assertIn("&#xEB42;", g, g[:200])

    def test_uk_evidence_is_merged(self):
        """USourceData.txt は UTC 文書の通し番号しか持っていないので、
        英国の提出文書にある書名とページを足す。"""
        r = next(x for x in self.rows if ">UK-02847<" in x)
        self.assertIn("Hanyu Fangyan Da Cidian", r)
        self.assertIn("IRG N2107R2", r)

    def test_ids_operators_are_substituted(self):
        """⿰⿱⿳ は持っていないフォントが多いので字形に差し替える。"""
        for r in self.rows[:200]:
            left = html.unescape(visible(glyph_cell(r)))
            self.assertFalse(re.search(r"[⿰-⿿]", left),
                             f"IDS の記号が差し替えられていない: {left[:12]}")


class SpoofingTest(PageTest):
    slug, category = "spoofing", "all"

    def test_every_row_shows_its_partner(self):
        """相手を並べないと比べようがないので、全行に出ていること。"""
        for r in self.rows:
            self.assertIn('class="pair"', r, "相手が出ていない行がある")

    def test_partner_column_is_never_hidden(self):
        """狭い画面でも相手の列を隠さない。

        提案文書の列は中身が無い行が多いので狭い画面では隠しているが、
        ここは必ず中身がある。同じ仕組みを流用すると丸ごと消えてしまう。
        """
        self.assertNotIn('class="ev nothing"', self.html)

    def test_both_sides_use_the_same_glyph_source(self):
        """本体と相手で字形の出所が違うと、線の太さが揃わず比べられない。"""
        for m in re.finditer(r'<img class="pg" src="([^"]+)"', self.html):
            self.assertTrue(m.group(1).startswith("../glyphs/"), m.group(1))

    def test_partner_shows_radical_and_translation(self):
        """相手の欄にも部首と訳を出す。ここが比べる場所なので、本体と同じだけ
        出ていないと違いが見えない。

        U+3B35 と U+80F6 は字形が 1 バイトも違わず、部首 (74 月 / 130 肉) と
        字義でしか見分けが付かない。
        """
        r = next(x for x in self.rows if f'data-cp="{0x3B35}"' in x)
        ev = re.search(r'<td class="ev">(.*?)</td>', r, re.S).group(1)
        self.assertIn("部首 130 肉", ev)
        self.assertIn("にかわ", ev)
        # 本体のほうは 74 月
        idc = re.search(r'<td class="id">(.*?)</td>', r, re.S).group(1)
        self.assertIn("部首 74 月", idc)

    def test_partner_uses_the_same_rule(self):
        """相手の字形も日本の形を優先する。

        片方だけ既定の形にすると、字形の差なのか国の差なのかが分からなくなる。
        日本のソースが無い字は既定に落ちる (U+29C18 など)。
        """
        from common import GLYPHS
        for m in re.finditer(r'class="pg" src="\.\./glyphs/(u[0-9a-f]+)\.svg"', self.html):
            self.assertFalse((GLYPHS / f"{m.group(1)}-j.svg").exists(),
                             f"{m.group(1)} は日本の形があるのに使っていない")

    def test_relation_is_closed(self):
        """相互に登録されていること (片側だけだと相手から辿れない)。"""
        from common import spoofing_pairs, unihan
        pairs = spoofing_pairs(unihan())
        for cp, ts in pairs.items():
            for t in ts:
                self.assertIn(t, pairs, f"{cp} の相手 {t} に登録が無い")
                self.assertIn(cp, pairs[t], f"{t} から {cp} へ戻れない")


class NavTest(PageTest):
    """一覧の上に貼り付けてある行。どのコレクションでも同じ。"""

    def test_nav_stays_in_this_tab(self):
        """同じサイトの中の移動で別のタブを開かない。

        原典へ飛ぶリンクは target=_blank で良いが、コレクションの行は
        押すたびにタブが増えてしまう。
        """
        nav = re.search(r'<nav class="nav">(.*?)</nav>', self.html, re.S).group(1)
        self.assertNotIn("target=", nav, nav)
        self.assertIn('href="../"', nav)
        self.assertIn('href="../lucky/"', nav)

    def test_nav_is_pinned(self):
        """スクロールしても残ること。下の帯はその高さぶん下げる。"""
        self.assertRegex(self.html, r"\.nav \{[^}]*position:sticky[^}]*top:0")
        self.assertRegex(self.html, r"\.bar \{[^}]*top:var\(--navh")

    def test_chips_fold_on_narrow(self):
        """狭い画面ではチップを畳む。貼り付ける帯が画面を食いすぎるため。"""
        narrow = self.html[self.html.index("@media (max-width: 900px)"):]
        self.assertRegex(narrow, r"\.chips \{[^}]*display:none")
        self.assertIn(".chips.open", narrow)
        self.assertIn('id="chiptog"', self.html)


class LuckyPageTest(unittest.TestCase):
    """ひとつずつ引くページ。4 つの一覧を合わせた母集団から 1 字ずつ出す。"""

    @classmethod
    def setUpClass(cls):
        import build_lucky
        from common import DOCS
        cls.counts = {}
        for c in toml("collections.toml")["collection"]:
            m = DOCS / c["slug"] / "meta.json"
            if m.exists():
                cls.counts[c["slug"]] = json.loads(m.read_text(encoding="utf-8"))["count"]
        build_lucky.main()
        cls.html = (DOCS / "lucky" / "index.html").read_text(encoding="utf-8")

    def test_holds_no_characters(self):
        """字はこのページに持たせない。一覧から切り出して貼る。

        字ごとのページを 5,000 枚書き出すと、同じ内容が 2 か所になる。
        """
        self.assertNotIn('<tr data-search=', self.html)
        self.assertLess(len(self.html), 80_000, "字を抱えてしまっている")

    def test_pool_is_every_collection(self):
        """母集団は 4 つの一覧の合計。件数の比で選ぶので一様になる。"""
        cols = json.loads(re.search(r"const COLS=(\{.*?\});", self.html).group(1))
        self.assertEqual(cols, self.counts)
        self.assertIn(f"{sum(self.counts.values()):,} 字", self.html)

    def test_uses_the_same_style(self):
        """切り出した行が一覧と同じに見えること。CSS は 1 か所から使う。"""
        from build_html import STYLE
        self.assertIn(STYLE, self.html)


class HubTest(unittest.TestCase):
    """トップページ。"""

    @classmethod
    def setUpClass(cls):
        import build_index
        from common import DOCS
        build_index.main()
        cls.html = (DOCS / "index.html").read_text(encoding="utf-8")

    def test_has_the_lucky_entry(self):
        """上から眺めるには多すぎるので、ここから当たれるようにする。"""
        self.assertIn('href="lucky/"', self.html)
        self.assertIn("ひとつずつ見る", self.html)


def load_tests(loader, tests, pattern):
    """PageTest そのものは動かさない (子クラスだけ)。"""
    keep = unittest.TestSuite()
    for suite in tests:
        for t in suite:
            if type(t).__name__ != "PageTest":
                keep.addTest(t)
    return keep


if __name__ == "__main__":
    unittest.main()
