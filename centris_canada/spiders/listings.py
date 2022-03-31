from scrapy_splash import SplashRequest
import scrapy
import json
from scrapy.selector import Selector


class ListingsSpider(scrapy.Spider):
    name = 'listings'
    allowed_domains = ['www.centris.ca']
    http_user = 'user'
    http_pass = 'userpass'

    position = {
        'startPosition': 0
    }

    script = '''
        function main(splash, args)
          splash:on_request(function(request)
            if request.url:find('css') then
                request.abort()
            end
           end
          )
          splash.images_enabled = false
          splash.js_enabled = false
          assert(splash:go(args.url))
          assert(splash:wait(0.5))
          return splash:html()

        end
    '''

    def start_requests(self):
        yield scrapy.Request(
            url='https://www.centris.ca/UserContext/Lock',
            method='POST',
            headers={
                'x-requested-with': 'XMLHttpRequest',
                'content-type': 'application/json'
            },
            body=json.dumps({'uc': 0}),
            callback=self.generate_uck
        )

    def generate_uck(self, response):
        uck = response.body
        query = {
            "query": {
                "UseGeographyShapes": 0,
                "Filters": [
                    {
                        "MatchType": "CityDistrictAll",
                        "Text": "Montréal (All boroughs)",
                        "Id": 5
                    }
                ],
                "FieldsValues": [
                    {
                        "fieldId": "CityDistrictAll",
                        "value": 5,
                        "fieldConditionId": "",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "Category",
                        "value": "Residential",
                        "fieldConditionId": "",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "SellingType",
                        "value": "Rent",
                        "fieldConditionId": "",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "LandArea",
                        "value": "SquareFeet",
                        "fieldConditionId": "IsLandArea",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "RentPrice",
                        "value": 0,
                        "fieldConditionId": "ForRent",
                        "valueConditionId": ""
                    },
                    {
                        "fieldId": "RentPrice",
                        "value": 1500,
                        "fieldConditionId": "ForRent",
                        "valueConditionId": ""
                    }
                ]
            },
            "isHomePage": True
        }

        yield scrapy.Request(
            url="https://www.centris.ca/property/UpdateQuery",
            method="POST",
            body=json.dumps(query),
            headers={
                'Content-Type': 'application/json',
                'x-requested-with': 'XMLHttpRequest',
                'x-centris-uc': 0,
                'x-centris-uck': uck
            },
            callback=self.update_query
        )

    def update_query(self, response):
        yield scrapy.Request(
            url='https://www.centris.ca/Property/GetInscriptions',
            method='POST',
            body=json.dumps(self.position),
            headers={
                'Content-Type': 'application/json',
            },
            callback=self.parse
        )

    def parse(self, response):
        resp_dict = json.loads(response.body)
        html = resp_dict.get("d").get("Result").get("html")
        sel = Selector(text=html)
        listings = sel.xpath("//body/div")

        for item in listings:
            category = item.xpath(
                './/span[@class="category"]/div/text()').get().strip()
            price = item.xpath(
                './/div[@class="price"]/span[1]/text()').get().replace("\xa0", "")

            city = item.xpath(
                './/span[@class="address"]/div/text()').getall()[-1]
            rel_url = item.xpath(
                './/div[@class="shell"]/a/@href').get().replace("fr", "en")
            url_abs = f"https://www.centris.ca{rel_url}"

            yield SplashRequest(
                url=url_abs,
                endpoint='execute',
                callback=self.parse_summary,
                args={
                    'lua_source': self.script
                },
                meta={
                    'cat': category,
                    'price': price,
                    'city': city,
                    'link': url_abs,

                }
            )

        count = resp_dict.get("d").get("Result").get("count")
        inscNumberPerPage = resp_dict.get("d").get(
            "Result").get("inscNumberPerPage")

        if self.position["startPosition"] < 60:
            self.position["startPosition"] += inscNumberPerPage

            yield scrapy.Request(
                url='https://www.centris.ca/Property/GetInscriptions',
                method="POST",
                body=json.dumps(self.position),
                headers={
                    'Content-Type': 'application/json',
                },
                callback=self.parse
            )

    def parse_summary(self, response):
        descriptions = response.xpath(
            'normalize-space(//div[@itemprop="description"]/text())').get()
        address = response.xpath('//h2[@itemprop="address"]/text()').get()
        category = response.request.meta['cat']
        price = response.request.meta['price']
        city = response.request.meta['city']
        link = response.request.meta['link']

        yield {
            'Descriptions': descriptions,
            'Address': address,
            'Category': category,
            'Price': price,
            'Link': link
        }
