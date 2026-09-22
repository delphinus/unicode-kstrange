# unicode-kstrange

Unihan の provisional プロパティ **`kStrange`** が付いた漢字について、**その字がどこで使われていたのか**を
辿れるところまで辿り、字形付きの一覧にするスクリプト。

**生成物 (`docs/index.html`) はこのリポジトリに入れていない。** zi.tools から取った字義を含んでいて、
zi.tools は利用条件を公開していないため、再配布してよいかを確かめられないから。`make CATEGORY=all` で
手元に作れる。字義の訳語表 `data/zi_tools_ja.toml` も、キーが原文そのものなので同じ理由で入れていない。

## kStrange とは

CJK 統合漢字のうち「非典型的 (strange)」なものを集めて 12 カテゴリに分類した、Unihan の暫定プロパティ。
Unicode 14.0 (2021) で導入され、編者は Ken Lunde。Unicode 18.0 時点で 828 字に付いている。

| 値 | 意味 | 18.0 の件数 |
|---|---|---|
| I | Incomplete — 既存字の不完全形に見える | 347 |
| U | Unusual — 構造・部品配置が異様 | 238 |
| O | Odd Component — 記号的・奇妙な部品を含む | 52 |
| Y | Symmetric — 対称の部品を並べている | 51 |
| H | Hangul Component — ハングルの部品を含む | 34 |
| M | Mirrored — 鏡像またはその部品を含む | 27 |
| S | Stroke-heavy — 40 画以上 | 26 |
| B | Bopomofo — 注音字母に似る | 23 |
| R | Rotated — 回転またはその部品を含む | 23 |
| C | Cursive — 筆記体的で楷書の筆画慣習に従わない | 22 |
| K | Katakana Component — カタカナに見える部品を含む | 21 |
| A | Asymmetric — 構造が非対称 | 5 |

生成物は 828 字すべてを 1 枚にしたもので、カテゴリで絞り込める。`CATEGORY` を変えれば
1 カテゴリだけの版も作れる。

## 使い方

```sh
make CATEGORY=all   # 入力取得 → 字形取得 → Wiktionary 確認 → HTML 生成 (828 字)
make                # カテゴリ S だけ (既定)
make CATEGORY=B     # 別のカテゴリ
open docs/index.html
```

Python 3.11 以上のみ (標準ライブラリだけで動く)。`make test-browser` だけ bun と Chrome を使う。

## テスト

```sh
make test          # 生成物の中身。2 秒、ブラウザ不要
make test-browser  # 画面の挙動。30 秒、bun と Chrome が要る
```

並べてあるのは**実際に踏んだ不具合**で、思い付きの網羅ではない。`tests/test_pages.py`
は組み立てた HTML を直接見る (字形の参照先、リンクの入れ子、まだ無いページへのリンク、
札の長さ、差し替えた字が検索から落ちていないか…)。`tests/browser/site.test.ts` は
ヘッドレス Chrome で、絞り込みと再読み込みの復元、横に溢れないこと、
900px での切り替え、暗い配色での字形、フォントの読み込みを見る。

| ターゲット | 中身 |
|---|---|
| `make fetch` | Unihan.zip / Blocks.txt / USourceData.txt / UTN #43 の PDF を `cache/` へ。版と SHA-256 を `cache/manifest.json` に記録する |
| `make glyphs` | 対象の字の字形 SVG を GlyphWiki から `docs/glyphs/` へ |
| `make wiktionary` | 英語版 Wiktionary に項目がある字を調べて `cache/` に残す (無い字にリンクを張らないため) |
| `make zi-tools` | zi.tools の API から字義と、その典拠になっている字書・論文を `cache/` へ。828 字ぶんで 30 分ほど掛かる。途中で止めても、もう一度流せば残りだけ取る |
| `make uk-source` | UK-source の提出文書 3 通を `cache/` へ落とし、抱えている Excel から字ごとの用例証拠を取り出す |
| `make l2docs` | `USourceData.txt` が挙げる UTC 文書 (L2/…) の題名・著者・PDF の URL を `cache/` へ |
| `make html` | `docs/index.html` を組み立てる |
| `make test` | 生成物の中身を確かめる。標準ライブラリだけで動き、ブラウザは要らない |
| `make test-browser` | 画面の挙動を確かめる。bun と Chrome が要る (無ければ飛ばす) |
| `make check-links` | 生成物のリンクを叩いて、開けないものを出す。`SAMPLE=15` でホストごとに 15 本だけ (828 字だと全部で 4,547 本あるため) |
| `make check-utn43` | UTN #43 の PDF の記述と Unihan の件数を比べる |

## 出典をどう辿っているか

1. **IRG ソース参照** (`kIRG_*Source`) の接頭辞を出典名に開く。`GKX-1381.18` なら「康熙字典 1381 ページ 18 字目」。
   対応表は [`data/irg_sources.toml`](data/irg_sources.toml)。
2. **字書索引** (`kKangXi` / `kHanYu` / `kSBGY` / `kMorohashi` ほか) を読める形にする。
   末尾の桁が 0 以外なら、その字書には実在せず並べ替え用に割り当てられた仮想位置なので、そう明記する。
3. **提案文書まで遡る**。ここは 2 段構えにしてある。
   - **自動**: UK-source の提出文書 3 通 (IRG N2107R2 / N2232R / N2487) は、字ごとの一覧を
     Excel ファイルとして PDF の中に抱えている。そこに用例証拠の書名・出版年・ページと図版番号が
     入っているので、`fetch_uk_source.py` が取り出す。U-source は `USourceData.txt` の出典欄を開き、
     `UTCDoc L2/…` は UTC の文書登録簿から題名・著者・PDF の URL を引く (`fetch_l2docs.py`)。
     出典欄に出てくる字書の略号は [`data/usource_tags.toml`](data/usource_tags.toml)。
   - **手書き**: 提案文書の本文まで読んで分かったことは [`data/notes.toml`](data/notes.toml)、
     書誌は [`data/books.toml`](data/books.toml) に書く。ある字は自動より手書きを優先する。
4. **zi.tools の字義を日本語にして並べる**。Unihan の英語の語釈 (`kDefinition`) は 828 字中 88 字にしか
   無いが、zi.tools の API には 754 字ぶんの字義がある。原文 (中国語・ベトナム語ほか) の下に訳を出す。
   訳は `data/zi_tools_ja.toml` に手で書いたもので (このリポジトリには入れていない)、「同=X」の形だけは
   数が多いので `build_html.py` が機械的に訳す。出典タグの対応は
   [`data/zi_tools_sources.toml`](data/zi_tools_sources.toml)。
5. **開けるものはリンクにする**。康熙字典は字頭検索、書籍は Amazon と国立国会図書館サーチ、
   提案文書は PDF、字ごとに zi.tools / 漢典 / Wiktionary / GlyphWiki / 文字情報基盤。
   Wiktionary は項目が無い字があるので、あらかじめ調べて**ある字にだけ**張る。

### 828 字でどこまで届いたか

| | 字数 |
|---|---|
| 康熙字典に実在し、字頭検索を開ける | 213 |
| 康熙字典の位置を持つが仮想位置 (実在しない) | 342 |
| 漢語大字典の位置が分かる (リンクは無い) | 390 |
| 文字情報基盤 (MJ) の項目がある | 435 |
| Wiktionary に項目がある | 446 |
| 何らかの字書索引を持つ | 558 (持たない字が 270) |
| 英語の語釈 (`kDefinition`) がある | 88 |
| zi.tools の字義がある (日本語訳を付けた) | 754 |
| そのうち典拠の字書・論文まで併記されている | 146 |
| 提案文書の用例証拠まで辿れる | 67 (手書きのメモ 10 / UK-source 35 / U-source 22) |

zi.tools・漢典・GlyphWiki・Unihan は 828 字すべてに項目がある。

### カテゴリ S で分かったこと

- **84 画の 𱁬 (U+3106C)** — 大野史朗・藤田豊『難読姓氏辞典』(東京堂出版, 1977) 213 ページ、
  馬場雄二『直感力が身につく「漢字・熟語」クイズ』(PHP 研究所, 2011) 52 ページ。姓として記録された字。
  zi.tools の字義は「「䨺龘」的合字。用於人名、店鋪名」。
- **76 画の 𰽔 (U+30F54)** — 宮沢賢治『農民とともに』(日本青年館, 1940) 58 ページ、
  『ザ・ベストハウス図鑑』(扶桑社, 2007) 135 ページ。
- **biáng の繁体 𰻞 (U+30EDE)** — 典拠が英語版 Wikipedia の記事 (2007-10-31 時点の版)。
  UAX #45 の中でも珍しく、辞書でも提案文書でもなく Web ページが出典になっている。
- **64 画の 𱟛 (U+317DB)** — 潮州語の字。《潮语十五音》の古い版に載り、意味は「恋」、音は soih⁴。
- **𲔁 (U+32501) と 𳅃 (U+33143)** — どちらも地名「天橋立」に関わる字。
- **𱱆 (U+31C46)** — 青銅器の金文 (Cook &amp; Goldin, *A Source Book of Ancient Chinese Bronze Inscriptions*, 2016)。

### リンクを付けられなかったもの

- **漢語大字典** — 自由に読めるページ画像が見つからない。巻・ページ・字順は載せているので、
  紙か商用の電子版で引く必要がある。
- **大漢和辞典・宋本広韻・大字源** — 自由に読めるオンライン版が無い。番号のみ載せている。
- **康熙字典のページ画像** — 康熙字典網上版は同文書局原版のスキャンを持っていて、Unihan の
  `kKangXi` のページ番号がそのまま画像の番号 (`/kangxi/<4 桁>.gif`) に対応する。ただし画像は
  Referer でホットリンクを弾いていて、外部のページから辿ると別の画像へ飛ばされる。
  そのため画像ではなく同サイトの字頭検索へリンクしている。
- 論文「Biáng 形纹样探究」、《潮语十五音》、韓国歴史情報統合システム — 字ごとに開ける形の
  オンライン版を見つけられなかった。
- **zi.tools の出典タグのうち `GHZH` と `FANGYAN`** — 前者は 6 桁の通し番号を持つ字書、
  後者は方言の調査資料だが、zi.tools 側にタグの一覧が無く、何の略かを確かめられなかった。
  推測で名前を付けず、タグのまま出している。
- **UK-source の証拠画像** — 提出文書の添付表には図版番号 (`Fig. 1700`、`UK-10126.png` など) が
  入っているが、画像そのものは別配布 (N2487 のぶんは 398 MB の ZIP) なので、番号だけ載せている。

## 字形について

字形は **GlyphWiki の SVG** を `docs/glyphs/` に置いている。GlyphWiki の
[データ・記事のライセンス](https://glyphwiki.org/wiki/GlyphWiki:%E3%83%87%E3%83%BC%E3%82%BF%E3%83%BB%E8%A8%98%E4%BA%8B%E3%81%AE%E3%83%A9%E3%82%A4%E3%82%BB%E3%83%B3%E3%82%B9)
は「あらゆる改変の有無に関わらず、また商業的な利用であっても、自由に利用、複製、再配布することができます」
としているため、同梱して配布できる。

置いてあるのは表に出す 828 字だけではない。**字義や用例の文中に出てくる字**も拡張 A 以降のものが多く、
macOS の標準フォントでは豆腐になる (例: U+200EC の字義に出てくる U+20DCE)。`fetch_glyphs.py` は
本文を走査してそういう字の SVG も取り、`build_html.py` が `<img>` に差し替える。字そのものは
見えない形で併記してあるので、**選択してコピーすれば字のまま取れるし、ページ内検索にも乗る**。
差し替える範囲は `common.py` の `needs_glyph()` — 拡張 A (U+3400-4DBF) と U+20000 以降。

**UK-source の字形だけは GlyphWiki ではなく、提出文書そのものから取っている。**
IRG N2107R2 / N2232R / N2487 は代表字形の TrueType を添付として抱えていて、字ごとの
私用領域コードポイントが添付の Excel に載っている。3,409 件の SVG を GlyphWiki から
取るより速いうえ、英国が「この形で」と出した字形そのもの。3,640 件すべてで引けることを
確かめてある。フォントは `fetch_uk_source.py` が `docs/fonts/` に取り出す
(リポジトリには入れない。Arphic Public License)。

UTN #43 の PDF の Ideograph 列から代表字形を切り出すこともできる (そちらが Unicode の代表字形そのもの) が、
Unicode の Terms of Use が公衆への配布を目的とした複製・改変を禁じているので、
**このリポジトリには入れない**。手元で見比べたいときだけ切り出す想定で、出力先の
`docs/glyphs-utn43/` は `.gitignore` に入れてある。

## 出所

| もの | 出所 |
|---|---|
| Unihan / UCD | [Unicode 18.0.0](https://www.unicode.org/Public/18.0.0/ucd/) (取得時の SHA-256 は生成物の見出しに出る) |
| kStrange の定義 | [UAX #38](https://www.unicode.org/reports/tr38/) / [UTN #43](https://www.unicode.org/notes/tn43/) (Ken Lunde) |
| U-source の提案文書 | [UAX #45](https://www.unicode.org/reports/tr45/) と UTC 文書 (L2/…)。題名と PDF の URL は年ごとの[文書登録簿](https://www.unicode.org/L2/L2020/Register-2020.html) |
| UK-source の提案文書 | [unicode-org/uk-source-ideographs](https://github.com/unicode-org/uk-source-ideographs) の IRG N2107R2 / N2232R / N2487 |
| 字義 | [zi.tools (字統網)](https://zi.tools/) の API (`/api/zi/<字>`)。日本語訳はこのリポジトリで付けたもの |
| 字形 | [GlyphWiki](https://glyphwiki.org/) |
| 康熙字典 | [康熙字典網上版](https://kangxizidian.com/) の字頭検索 |

## ライセンス

スクリプトと `data/` 以下の記述は MIT License ([LICENSE](LICENSE))。
`docs/glyphs/` の SVG は GlyphWiki 由来で、上記のとおり自由に利用できる。
Unihan から取り出した値と、UK-source の用例証拠 (提出文書の添付表から取り出したもの) は
Unicode, Inc. のもので、[Unicode License v3](https://www.unicode.org/license.txt) に従う。
同ライセンスが求める copyright and permission notice は [LICENSE-unicode](LICENSE-unicode) に置いた。

**zi.tools の字義は、このリポジトリにも生成物にも入れていない。** [zi.tools](https://zi.tools/) は
利用条件のページを持っておらず (`/about` `/terms` `/license` はいずれも SPA の同じ応答を返すだけで、
`robots.txt` も無い)、再配布してよいかを確かめられなかったため。`make zi-tools` で手元に取れば、
手元の生成物には出る。
