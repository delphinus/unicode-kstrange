# unicode-kstrange

Unihan の provisional プロパティ **`kStrange`** が付いた漢字について、**その字がどこで使われていたのか**を
辿れるところまで辿り、字形付きの一覧にするスクリプトと、その生成物。

生成物: <https://delphinus.github.io/unicode-kstrange/>

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

Python 3.11 以上のみ (標準ライブラリだけで動く)。`make check-utn43` だけ poppler (`pdftotext`) を使う。

| ターゲット | 中身 |
|---|---|
| `make fetch` | Unihan.zip / Blocks.txt / USourceData.txt / UTN #43 の PDF を `cache/` へ。版と SHA-256 を `cache/manifest.json` に記録する |
| `make glyphs` | 対象の字の字形 SVG を GlyphWiki から `docs/glyphs/` へ |
| `make wiktionary` | 英語版 Wiktionary に項目がある字を調べて `cache/` に残す (無い字にリンクを張らないため) |
| `make html` | `docs/index.html` を組み立てる |
| `make check-links` | 生成物のリンクを叩いて、開けないものを出す。`SAMPLE=15` でホストごとに 15 本だけ (828 字だと全部で 4,547 本あるため) |
| `make check-utn43` | UTN #43 の PDF の記述と Unihan の件数を比べる |

## 出典をどう辿っているか

1. **IRG ソース参照** (`kIRG_*Source`) の接頭辞を出典名に開く。`GKX-1381.18` なら「康熙字典 1381 ページ 18 字目」。
   対応表は [`data/irg_sources.toml`](data/irg_sources.toml)。
2. **字書索引** (`kKangXi` / `kHanYu` / `kSBGY` / `kMorohashi` ほか) を読める形にする。
   末尾の桁が 0 以外なら、その字書には実在せず並べ替え用に割り当てられた仮想位置なので、そう明記する。
3. **提案文書まで遡る**。U-source の字は `USourceData.txt` の文書番号から UTC 文書 (L2/…) を、
   UK-source の字は英国の IRG 提出文書 (N2107R2 / N2232R) の証拠一覧と参考文献表を読む。
   ここで出てきた書誌は [`data/books.toml`](data/books.toml)、字ごとのメモは [`data/notes.toml`](data/notes.toml) に手で書く。
4. **開けるものはリンクにする**。康熙字典はページ画像、書籍は Amazon と国立国会図書館サーチ、
   提案文書は PDF、字ごとに zi.tools / 漢典 / Wiktionary / GlyphWiki / 文字情報基盤。
   Wiktionary は項目が無い字があるので、あらかじめ調べて**ある字にだけ**張る。

### 828 字でどこまで届いたか

| | 字数 |
|---|---|
| 康熙字典のページ画像を直接開ける | 555 |
| 漢語大字典の位置が分かる (リンクは無い) | 390 |
| 文字情報基盤 (MJ) の項目がある | 435 |
| Wiktionary に項目がある | 446 |
| 何らかの字書索引を持つ | 558 (持たない字が 270) |
| 英語の語釈 (`kDefinition`) がある | 88 |
| 提案文書まで遡ってメモを書いた | 10 |

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
- 論文「Biáng 形纹样探究」、《潮语十五音》、韓国歴史情報統合システム — 字ごとに開ける形の
  オンライン版を見つけられなかった。

## 字形について

字形は **GlyphWiki の SVG** を `docs/glyphs/` に置いている。GlyphWiki の
[データ・記事のライセンス](https://glyphwiki.org/wiki/GlyphWiki:%E3%83%87%E3%83%BC%E3%82%BF%E3%83%BB%E8%A8%98%E4%BA%8B%E3%81%AE%E3%83%A9%E3%82%A4%E3%82%BB%E3%83%B3%E3%82%B9)
は「あらゆる改変の有無に関わらず、また商業的な利用であっても、自由に利用、複製、再配布することができます」
としているため、同梱して配布できる。

UTN #43 の PDF の Ideograph 列から代表字形を切り出すこともできる (そちらが Unicode の代表字形そのもの) が、
Unicode の Terms of Use が公衆への配布を目的とした複製・改変を禁じているので、
**このリポジトリには入れない**。手元で見比べたいときだけ切り出す想定で、出力先の
`docs/glyphs-utn43/` は `.gitignore` に入れてある。

## 出所

| もの | 出所 |
|---|---|
| Unihan / UCD | [Unicode 18.0.0](https://www.unicode.org/Public/18.0.0/ucd/) (取得時の SHA-256 は生成物の見出しに出る) |
| kStrange の定義 | [UAX #38](https://www.unicode.org/reports/tr38/) / [UTN #43](https://www.unicode.org/notes/tn43/) (Ken Lunde) |
| U-source の提案文書 | [UAX #45](https://www.unicode.org/reports/tr45/) と UTC 文書 (L2/…) |
| UK-source の提案文書 | [unicode-org/uk-source-ideographs](https://github.com/unicode-org/uk-source-ideographs) |
| 字形 | [GlyphWiki](https://glyphwiki.org/) |
| 康熙字典のページ画像 | [康熙字典網上版](https://kangxizidian.com/) (同文書局原版) |

## ライセンス

スクリプトと `data/` 以下の記述は MIT License ([LICENSE](LICENSE))。
`docs/glyphs/` の SVG は GlyphWiki 由来で、上記のとおり自由に利用できる。
Unihan から取り出した値そのものは Unicode, Inc. の
[Terms of Use](https://www.unicode.org/terms_of_use.html) に従う。
