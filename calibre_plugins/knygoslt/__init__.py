# -*- coding: utf-8 -*-
from calibre.ebooks.epub import pages
__license__ = 'GPL v3'
__copyright__ = '2019, Darau, blė <darau.ble@gmail.com>'
__docformat__ = 'restructuredtext lt'

import re
import urllib2
import datetime

from lxml import etree
from difflib import SequenceMatcher
from Queue import Queue, Empty

from calibre.utils.filenames import ascii_filename
from calibre.ebooks.metadata.book.base import Metadata
from calibre.ebooks.metadata.sources.base import Source

class Knygoslt(Source):
    
    name = "Knygos.lt"
    description = _("Parsiunčia knygų aprašymus iš Knygos.lt tinklapio")
    author = "Darau, blė"
    version = (0, 0, 2)
    minimum_calibre_version = (3, 0, 0)
    
    capabilities = frozenset(['identify', 'cover'])
    touched_fields = frozenset(['title', 'authors', 'tags', 'identifier:isbn', 'comments', 'publisher', 'pubdate', 'languages'
                                #, '#count'
                                ])
    has_html_comments = True
    supports_gzip_transfer_encoding = False
    
    ID_NAME = "isbn"
    BASE_URL = "https://www.knygos.lt/"
    BASE_LIST_REQ = BASE_URL + "lt/paieska/?q=%s"
    
    list_result_x = "//h3[@class='result-title']/a"
    
    details_author = "//p[@class='book_details']//a[@itemprop='author']"
    details_publisher = "//p[@class='book_details']/a[@itemprop='publisher']"
    details_year = u"//p[@class='book_details' and text()[contains(., 'Išleista')]]"
    details_pages = "//p[@class='book_details']/span[@itemprop='numberOfPages']"
    details_isbn = "//p[@class='book_details']/span[@itemprop='isbn']"
    details_description = "//div[@id='dvd_description']/div[@class='collapsable-box']"
    details_cover = "//div[@class='product-photo']/div/a"
    #details_tags = u"//div[@class='box_title']/h2[text()[contains(., 'Panašios prekes')]]/../../div[@class='box']/div/ul/li"
    details_tags = u"//div[@class='box_title']/h2[text()[contains(., 'Panašios prekės')]]/../../div[@class='box']/div/ul/li"
    
    filter_parent_tags = ['AKCIJOS', 'KNYGŲ MUGĖS naujienos!', 'Metų knygos rinkimai 2018', 'Užrašų knygos ir kalendoriai',
                          'Dovanų idėjos', 'Kanceliarinės prekės', 'Žaislai ir žaidimai', 'Žurnalai']
    
    clear_color = re.compile("color:\s*#[0-9a-f]+;?", re.IGNORECASE)
    clear_bg = re.compile("background:\s*#[0-9a-f]+;?", re.IGNORECASE)
    clear_ahref = re.compile("<a\s+href[^>]+?>", re.IGNORECASE)

    def get_book_url(self, identifiers):
        isbn = identifiers.get(self.ID_NAME, None)
        if isbn:
            url_list = self._get_urls(isbn, 1)
            if len(url_list):
                return (self.name, isbn, url_list[0]["url"])
        
        return None
    
    def identify(self, log, result_queue, abort, title=None, authors=None,
            identifiers={}, timeout=30):
        
        if identifiers and identifiers["isbn"]:
            log("identify:: gavom fakin ISBN:", identifiers["isbn"])
            url_list = self._get_urls(identifiers["isbn"], 1)
        elif title:
            book_name = ascii_filename(title).lower().replace(' ', '+').replace('-', '+').replace('--', '+').replace('_', '+').replace('.', '+').replace('++', '+')
            log("identify:: gavom title, query:", book_name)
            url_list = self._filter_urls(self._get_urls(book_name), title)
            
        else:
            return None
        
        if abort.is_set():
            return
        
        for url in url_list:
            if abort.is_set():
                return
            
            mi = self._get_bookdetails(url)
            if mi:
                result_queue.put(mi)
        
        return None
    
    def download_cover(self, log, result_queue, abort,
            title=None, authors=None, identifiers={}, timeout=30):
        
        cached_url = None
        if identifiers and identifiers["isbn"]:
            cached_url = self.cached_identifier_to_cover_url(identifiers["isbn"])
            
        if cached_url is None:
            log.info('No cached cover found, running identify')
            rq = Queue()
            self.identify(log, rq, abort, title=title, authors=authors,
                    identifiers=identifiers)
            if abort.is_set():
                return
            results = []
            while True:
                try:
                    results.append(rq.get_nowait())
                except Empty:
                    break
            results.sort(key=self.identify_results_keygen(
                title=title, authors=authors, identifiers=identifiers))
            for mi in results:
                if mi.identifiers["isbn"]:
                    cached_url = self.get_cached_cover_url(mi.identifiers["isbn"])
                if cached_url is not None:
                    break
                
        if cached_url is None:
            log.info('No cover found')
            return

        if abort.is_set():
            return
        br = self.browser
        log('Downloading cover from:', cached_url)
        try:
            cdata = br.open_novisit(cached_url, timeout=timeout).read()
            result_queue.put((self, cdata))
        except:
            log.exception('Failed to download cover from:', cached_url)
            
        return

    def is_configured(self):
        return True
    
    def _get_urls(self, query, count=0):
        #book_name = ascii_filename(book_meta.title).lower().replace(' ', '+').replace('-', '+').replace('--', '+').replace('_', '+').replace('.', '+').replace('++', '+')
        print("Pakvietem knygos.lt booklist %s" % query)
        resp = urllib2.urlopen(self.BASE_LIST_REQ % query)
        contents = resp.read()
        #print(contents)
        tree = etree.HTML(contents)
        
        book_results = tree.xpath(self.list_result_x)
        books = []
        
        if len(book_results):
            cnt = 0
            for br in book_results:
                books.append({"url": br.attrib["href"], "title": br.text})
                cnt += 1
                if count > 0 and cnt >= count:
                    break
                #print(br.attrib['href'], br.text)
        
        return books
    
    def _filter_urls(self, urls, title):
        filtered_urls = []
        
        for url in urls:
            test_title = url["title"].lower()
            if len(test_title) > len(title):
                test_title = test_title[:len(title)]
            print("_filter_urls:: test title: ", test_title)
            ratio = SequenceMatcher(None, title.lower(), test_title).ratio()
            print("_filter_urls:: matching ", title.lower(), "against", test_title, "; ratio:", ratio)
            if ratio > 0.75:
                print("\t...matched!")
                filtered_urls.append(url)
        
        return filtered_urls
    
    def _get_bookdetails(self, url):
        u = self.BASE_URL+url["url"]
        print("_get_bookdetails:: traukiam knygą iš %s" % u)
        
        resp = urllib2.urlopen(u)
        contents = resp.read()
        #print(contents)
        tree = etree.HTML(contents)
        
        authors = self._get_authors(tree)
        publisher = self._get_details(tree, self.details_publisher)
        year = self._get_year(tree)
        pages = self._get_details(tree, self.details_pages)
        isbn = self._get_details(tree, self.details_isbn)
        description = self._get_description(tree)
        cover = self._get_cover_url(tree)
        tags = self._get_tags(tree)
        
        mi = Metadata(url["title"], authors)
        mi.set_identifier("isbn", isbn)
        mi.comments = description
        mi.language = "LT";
        mi.tags = tags
        try:
            mi.set("publisher", publisher)
        except:
            print(u"_get_bookdetails:: nepavyko užsetinti leidėjo")
        try:
            mi.set("pubdate", datetime.datetime(year, 1, 2))
        except:
            print(u"_get_bookdetails:: nepavyko užsetinti leidimo datos")
        try:
            if self.gui:
                print("YYYYRAAA GUI!!!")
            col = {};
            col["#value#"] = pages
            mi.set_user_metadata("#count", col)
        except:
            print(u"_get_bookdetails:: nepavyko užsetinti puslapių skaičiaus")
        
        if cover and isbn:
            print(u"_get_bookdetails:: kešuojam viršelį:", cover)
            self.cache_isbn_to_identifier(isbn, isbn)
            self.cache_identifier_to_cover_url(isbn, cover)
            mi.has_cover = True
            
            print(self.cached_identifier_to_cover_url(isbn))
        
        return mi
    
    def _get_authors(self, tree):
        authors = tree.xpath(self.details_author)
        
        aret = []
        if len(authors):
            for a in authors:
                aret.append(a.text)
                
        return aret
    
    def _get_details(self, tree, path):
        details = tree.xpath(path)
        if len(details):
            for d in details:
                return d.text
        
        return None
    
    def _get_year(self, tree):
        years = tree.xpath(self.details_year)
        if len(years):
            for year in years:
                return int(year.text[10:])

        return None
        
    def _get_description(self, tree):
        desc = tree.xpath(self.details_description)
        if len(desc):
            for d in desc:
                description = etree.tostring(d)
                description = self.clear_color.sub("", description)
                description = self.clear_bg.sub("", description)
                description = self.clear_ahref.sub("", description)
                description = description.replace("</a>", "")
                return description
        
        return ""
    
    def _get_cover_url(self, tree):
        link = tree.xpath(self.details_cover)
        url = None
        if len(link):
            for l in link:
                url = l.attrib["href"]
                print("_get_cover_url:: pradinis URL:", url)
                break
        
        start = url.find("/images/books")
        if start >= 0:
            url = self.BASE_URL + url[start+1:]
            print("_get_cover_url:: perdirbtas URL:", url)
        
        return url
    
    def _get_tags(self, tree):
        print("_get_tags:: start")
        tags = []
        tags_dict = {}
        tag_list = tree.xpath(self.details_tags)
        
        if len(tag_list):
            for tag_line in tag_list:
                for tag in tag_line:
                    if tag.tag == "a" and tag.text not in self.filter_parent_tags:
                        print("_get_tags:: tag:", tag.text)
                        tags_dict[tag.text] = 1
                    else:
                        print("_get_tags:: filter", tag.text)
                        break
        
        for k, v in tags_dict.items():
            tags.append(k)
            
        return tags

if __name__ == '__main__': # tests
        # To run these test use:
    # calibre-debug -e __init__.py
    from calibre.ebooks.metadata.sources.test import (test_identify_plugin,
            title_test, authors_test)

    test_identify_plugin(Knygoslt.name,
        [
            (# Knyga pagal viršelį
                {'title':u'Tėvas Gorijo'},
                [title_test(u'Tėvas Gorijo', exact=True)]
            ),
        ])
            
    '''
            (# Knyga pagal viršelį
                {'title':'Helenos paslaptis'},
                [title_test('Helenos paslaptis', exact=True),
                 authors_test(['Lucinda Riley'])]
            ),
            (# Knyga pagal viršelį
                {'title':'Puritonai', 'authors':['Walter Scott']},
                [title_test('Puritonai', exact=True),
                 authors_test(['Walter Scott'])]
            ),

            (# Knyga pagal ISBN
                {'identifiers':{'isbn': '9786094663680'}},
                [title_test(u'Gyvybė 3.0: žmogus dirbtinio intelekto amžiuje', exact=True),
                 authors_test(['Max Tegmark'])]
            ),
            
            (# Knyga baltu tekstu, bandyti nuvalyti
                {'title':u'DRAUGAS'},
                [title_test(u'DRAUGAS: kuo pasitikėti, kai tave medžioja draugai?', exact=True),
                 authors_test([u'Darius Tauginas'])]
            ),
    (# Knyga su keliais viršeliais, imti pirmą
        {'title':u'PROTINGAS GROŽIS: švytinčios odos biblija'},
        [title_test(u'PROTINGAS GROŽIS: švytinčios odos biblija + PRAKTINĖ MAKIAŽO KNYGA', exact=True),
         authors_test([u'Indrė Urbanavičienė'])]
    ),
    '''
    