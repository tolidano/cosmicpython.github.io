#!/usr/bin/env python
from dataclasses import dataclass
from pathlib import Path
import json
from lxml import html
import subprocess

BOOK_SOURCE = Path('../book')
DEST = Path('./book')

CHAPTERS = [
    c.replace('.asciidoc', '.html')
    for c in json.loads((BOOK_SOURCE / 'atlas.json').read_text())['files']
    if c.partition('.')[0] not in [
        'cover',
        'titlepage',
        'copyright',
        'toc',
        'ix',
        'author_bio',
        'colo',
    ]
]




def parse_chapters():
    for chapter in CHAPTERS:
        path = BOOK_SOURCE / chapter
        yield chapter, html.fromstring(path.read_text())


def get_anchor_targets(parsed_html):
    ignores = {'header', 'content', 'footnotes', 'footer', 'footer-text'}
    all_ids = [
        a.get('id') for a in parsed_html.cssselect('*[id]')
    ]
    return [i for i in all_ids if not i.startswith('_') and i not in ignores]

@dataclass
class ChapterInfo:
    href_id: str
    chapter_title: str
    old_title: str
    subheaders: list
    xrefs: list

    @property
    def url(self):
        return f"/book/{self.href_id}.html"



def get_chapter_info():
    chapter_info = {}
    appendix_numbers = list('ABCDEFGHIJKL')
    chapter_numbers = list(range(1, 100))
    part_numbers = list(range(1, 10))

    for chapter, parsed_html in parse_chapters():
        print('getting info from', chapter)

        if not parsed_html.cssselect('h2'):
            header = parsed_html.cssselect('h1')[0]
        else:
            header = parsed_html.cssselect('h2')[0]
        href_id = header.get('id')
        if href_id is None:
            href_id = parsed_html.cssselect('body')[0].get('id')
        subheaders = [h.get('id') for h in parsed_html.cssselect('h3')]

        old_title = header.text_content()
        chapter_title = old_title.replace('Appendix A: ', '')

        if chapter.startswith('chapter_'):
            chapter_no = chapter_numbers.pop(0)
            chapter_title = f'{chapter_no}: {chapter_title}'

        if chapter.startswith('appendix_'):
            appendix_no = appendix_numbers.pop(0)
            chapter_title = f'Appendix {appendix_no}: {chapter_title}'

        if chapter.startswith('part'):
            part_no = part_numbers.pop(0)
            chapter_title = f'Part {part_no}: {chapter_title}'

        if chapter.startswith('epilogue'):
            chapter_title = f'Epilogue: {chapter_title}'

        xrefs = get_anchor_targets(parsed_html)
        chapter_info[chapter] = ChapterInfo(
            href_id, chapter_title, old_title, subheaders, xrefs
        )

    return chapter_info


def fix_xrefs(contents, chapter, chapter_info):
    parsed = html.fromstring(contents)
    links = parsed.cssselect(r'a[href^=\#]')
    for link in links:
        for other_chap in CHAPTERS:
            if other_chap == chapter:
                continue
            chapter_id = chapter_info[other_chap].href_id
            href = link.get('href')
            targets = ['#' + x for x in chapter_info[other_chap].xrefs]
            if href == '#' + chapter_id:
                link.set('href', f'/book/{other_chap}')
            elif href in targets:
                link.set('href', f'/book/{other_chap}{href}')

    return html.tostring(parsed)


def _strip_keeptogethers(el):
    for child in el.cssselect('span.keep-together'):
        el.remove(child)


def fix_title(contents, chapter, chapter_info):
    parsed = html.fromstring(contents)
    titles = parsed.cssselect('h2')
    if titles:
        title = titles[0]
        _strip_keeptogethers(title)
        title.text = chapter_info[chapter].chapter_title
    return html.tostring(parsed)

def _prep_prev_and_next_buttons(chapter, chapter_info, buttons_html):
    buttons_div = html.fromstring(buttons_html)
    # rely on python 3.7+ dict ordering
    chap_index = list(chapter_info.keys()).index(chapter)
    [prev_link] = buttons_div.cssselect('a.prev_chapter_link')
    [next_link] = buttons_div.cssselect('a.next_chapter_link')
    if chap_index >= 0:
        prev_chapinfo = list(chapter_info.values())[chap_index - 1]
        prev_link.set('href', prev_chapinfo.url)
        prev_link.text = f'<< Previous - {prev_chapinfo.chapter_title}'
    else:
        prev_link.getparent().remove(prev_link)
    try:
        next_chapinfo = list(chapter_info.values())[chap_index + 1]
        next_link.set('href', next_chapinfo.url)
        next_link.text = f'Next - {next_chapinfo.chapter_title} >>'
    except IndexError:
        next_link.getparent().remove(next_link)
    return buttons_div



def copy_chapters_across_with_fixes(chapter_info, fixed_toc):
    comments_html = Path('fragments/disqus_comments.html').read_text()
    buttons_html = Path('fragments/prev_and_next_chapter_buttons.html').read_text()
    buy_book_div = html.fromstring(
        Path('fragments/buy_the_book_banner.html').read_text()
    )
    analytics_div = html.fromstring(
        Path('fragments/google_analytics.html').read_text()
    )

    for chapter in CHAPTERS:
        chapinfo = chapter_info[chapter]
        old_contents = (BOOK_SOURCE / chapter).read_text()
        new_contents = fix_xrefs(old_contents, chapter, chapter_info)
        new_contents = fix_title(new_contents, chapter, chapter_info)
        parsed = html.fromstring(new_contents)
        body = parsed.cssselect('body')[0]
        if header := parsed.cssselect('#header'):
            body.set('class', 'article toc2 toc-left')
            header[0].append(fixed_toc)
        body.insert(0, buy_book_div)
        [content_div] = parsed.cssselect('#content')
        content_div.append(
            _prep_prev_and_next_buttons(chapter, chapter_info, buttons_html)
        )
        body.append(html.fromstring(
            comments_html.replace(
                'PAGE_IDENTIFIER', chapter.split('.')[0]
            ).replace(
                'PAGE_URL', chapinfo.url
            )
        ))
        body.append(analytics_div)
        fixed_contents = html.tostring(parsed)
        target = DEST / chapter
        print('writing', target)
        target.write_bytes(fixed_contents)



def extract_toc_from_book():
    parsed = html.fromstring((BOOK_SOURCE / 'book.html').read_text())
    return parsed.cssselect('#toc')[0]



def fix_toc(toc, chapter_info):
    href_mappings = {}
    title_mappings = {}
    for chapter in CHAPTERS:
        chapinfo = chapter_info[chapter]
        if chapinfo.href_id:
            href_mappings['#' + chapinfo.href_id] = f'/book/{chapter}'
        for subheader in chapinfo.subheaders:
            href_mappings['#' + subheader] = f'/book/{chapter}#{subheader}'
        if 'Appendix' in chapinfo.old_title:
            short_title = chapinfo.old_title.partition(':')[2].strip()
            title_mappings[short_title] = chapinfo.chapter_title
        if 'Part' in chapinfo.chapter_title:
            short_title = chapinfo.chapter_title.partition(':')[2].strip()
            title_mappings[short_title] = chapinfo.chapter_title


    for (el, attr, link, pos) in list(toc.iterlinks()):
        el.set('href', href_mappings[link])
        short_title = el.text_content().split(':', 1)[-1].strip()
        if 'Appendix' in el.text_content() or short_title in title_mappings:
            new_title = title_mappings[short_title]
            _strip_keeptogethers(el)
            el.text = new_title

    toc.set('class', 'toc2')
    return toc


def main():
    toc = extract_toc_from_book()
    chapter_info = get_chapter_info()
    fixed_toc = fix_toc(toc, chapter_info)
    copy_chapters_across_with_fixes(chapter_info, fixed_toc)


if __name__ == '__main__':
    main()
