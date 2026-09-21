CATEGORY ?= S
PY       ?= python3
SCRIPTS  := PYTHONPATH=scripts $(PY)

.PHONY: all fetch glyphs html check check-links check-utn43 clean distclean

all: fetch glyphs html

## 入力データ (Unihan ほか) を cache/ へ取得し、版とハッシュを記録する
fetch:
	$(SCRIPTS) scripts/fetch_inputs.py

## 対象の字の字形 SVG を GlyphWiki から docs/glyphs/ へ取得する
glyphs:
	$(SCRIPTS) scripts/fetch_glyphs.py --category $(CATEGORY)

## docs/index.html を組み立てる
html:
	$(SCRIPTS) scripts/build_html.py --category $(CATEGORY)

check: check-links check-utn43

## 生成物のリンクを全部叩く
check-links:
	$(SCRIPTS) scripts/check_links.py

## UTN #43 の PDF の記述と Unihan を比べる (poppler が要る)
check-utn43:
	$(SCRIPTS) scripts/check_utn43.py

## 生成物を消す (取得済みの入力は残す)
clean:
	rm -f docs/index.html
	rm -rf docs/glyphs

## 取得済みの入力も消す
distclean: clean
	rm -rf cache
