#!/usr/bin/env python
# copied from https://github.com/tonybaloney/tonybaloney.github.io/blob/master/blog-gen.py
from dataclasses import dataclass
from datetime import date, datetime, time
from email.utils import formatdate, format_datetime  # for RFC2822 formatting
from pathlib import Path

import jinja2
import markdown

TEMPLATE_FILE = "templates/blog_post_template.html"
FEED_TEMPLATE_FILE = "templates/rss_feed_template.xml"
BLOG_POSTS_PATH = Path("posts")
OUTPUT_DIR = Path(".")



@dataclass
class Post:
    title: str
    author: str
    md_path: Path
    date: date

    @property
    def html_path(self):
        return OUTPUT_DIR / "blog" / self.md_path.name.replace('.md', '.html')

    @property
    def url(self):
        return f"/blog/{self.html_path.name}"

    @property
    def rfc2822_date(self):
        return format_datetime(datetime.combine(self.date, time(12, 00)))


def main():
    md_post_paths = sorted(BLOG_POSTS_PATH.glob("*.md"))
    extensions = ['extra', 'smarty', 'meta', 'codehilite']
    _md = markdown.Markdown(extensions=extensions, output_format='html5')

    loader = jinja2.FileSystemLoader(searchpath="./")
    env = jinja2.Environment(loader=loader)

    all_posts = []
    for md_post_path in md_post_paths:
        # print("rendering", md_post_path)
        post_date = date.fromisoformat(md_post_path.name[:10])
        html_content = _md.convert(md_post_path.read_text())
        post = Post(
            md_path=md_post_path, date=post_date,
            author=_md.Meta['author'][0],
            title=_md.Meta['title'][0],
        )
        post_html = env.get_template(TEMPLATE_FILE).render(
            content=html_content, url=post.url, post=post,
            **_md.Meta,
        )
        print("writing", post.html_path)
        post.html_path.write_text(post_html)

        all_posts.append(post)

    # Order blog posts by date published
    all_posts.sort(key=lambda p: p.date, reverse=True)

    # index
    # print("rendering index.html")
    index_html = env.get_template('pages/index.html').render(
        posts=all_posts,
    )
    index_html_path = OUTPUT_DIR / 'index.html'
    print("writing", index_html_path)
    index_html_path.write_text(index_html)


    # Make the RSS feed
    rss_path = OUTPUT_DIR / "rss.xml"
    print("writing", rss_path)
    rss_path.write_text(
        env.get_template(FEED_TEMPLATE_FILE).render(
            posts=all_posts, date=formatdate()
        )
    )


if __name__ == "__main__":
    main()
