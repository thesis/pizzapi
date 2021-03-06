from copy import deepcopy
import requests

from .menu import Menu
from .proxy import ProxyMeta
from .urls import Urls, COUNTRY_USA 
from .utils import TIMEOUT


# TODO: Add add_coupon and remove_coupon methods
class Order(metaclass=ProxyMeta):
    """Core interface to the payments API.

    The Order is perhaps the second most complicated class - it wraps
    up all the logic for actually placing the order, after we've
    determined what we want from the Menu. 

    Args:
    - data - a preinitialized order object
    """
    def __init__(self, store, customer, address, country=COUNTRY_USA, service='Carryout', data=None, order_id='', menu_data=None):
        self.store = store
        self.menu = Menu(data=menu_data) if menu_data else Menu.from_store(store_id=store.id, country=country)
        self.customer = customer
        self.address = address
        self.urls = Urls(country)
        assert service in ['Carryout', 'Delivery']
        self.data = {
            'Address': self.address.data,
            'Coupons': [], 'CustomerID': '', 'Extension': '',
            'OrderChannel': 'OLO', 'OrderID': order_id, 'NoCombine': True,
            'OrderMethod': 'Web', 'OrderTaker': None, 'Payments': [],
            'Products': [], 'Market': '', 'Currency': '',
            'ServiceMethod': service, 'Tags': {}, 'Version': '1.0',
            'SourceOrganizationURI': 'order.dominos.com', 'LanguageCode': 'en',
            'Partners': {}, 'NewUser': True, 'metaData': {}, 'Amounts': {},
            'BusinessDate': '', 'EstimatedWaitMinutes': '',
            'PriceOrderTime': '', 'AmountsBreakdown': {}
            }

        # Allow the caller to override some data
        if data:
            self.data = data
            self.data['Address'] = self.address.data
            self.data['ServiceMethod'] = service

    # TODO: Implement item options
    # TODO: Add exception handling for KeyErrors
    def add_item(self, code, qty=1, options={}):
        item = self.menu.variants[code]
        item = deepcopy(item)
        item.update(ID=1, isNew=True, Qty=qty, AutoRemove=False, Options=options)
        self.data['Products'].append(item)
        return item

    # TODO: Raise Exception when index isn't found
    def remove_item(self, code):
        codes = [x['Code'] for x in self.data['Products']]
        return self.data['Products'].pop(codes.index(code))

    def add_coupon(self, code, qty=1):
        self.data['Coupons'].append({'Code': code})

    def remove_coupon(self, code):
        codes = [x['Code'] for x in self.data['Coupons']]
        return self.data['Coupons'].pop(codes.index(code))

    def _send(self, url, merge, timeout=TIMEOUT):
        self.data.update(
            StoreID=self.store.id,
            Email=self.customer.email,
            FirstName=self.customer.first_name,
            LastName=self.customer.last_name,
            Phone=self.customer.phone,
            #Address=self.address.street

        )

        for key in ('StoreID', 'Address'):
            if key not in self.data or not self.data[key]:
                raise Exception('order has invalid value for key "%s"' % key)

        headers = {
            'Referer': 'https://order.dominos.com/en/pages/order/',
            'Content-Type': 'application/json'
        }

        r = requests.post(url=url, headers=headers, json={'Order': self.data}, timeout=timeout, proxies=self.proxies)
        r.raise_for_status()
        json_data = r.json()

        if merge:
            for key, value in json_data['Order'].items():
                if value or not isinstance(value, list):
                    self.data[key] = value
        return json_data

    # TODO: Figure out if this validates anything that self.urls.price_url() does not
    def validate(self):
        response = self._send(self.urls.validate_url(), True)
        return response['Status'] != -1

    # TODO: Actually test this
    def place(self, card=False, giftcards=[]):
        self.pay_with(card=card, giftcards=giftcards)
        response = self._send(self.urls.place_url(), False)
        return response

    # TODO: Add self.price() and update whenever called and items were changed
    def pay_with(self, card=False, giftcards=[]):
        """Use this instead of self.place when testing"""
        # get the price to check that everything worked okay
        response = self._send(self.urls.price_url(), True)
        
        if response['Status'] == -1:
            raise Exception('get price failed: %r' % response)

        if card:
            self.data['Payments'] = [
                {
                    'Type': 'CreditCard',
                    'Expiration': card.expiration,
                    'Amount': self.data['Amounts'].get('Customer', 0),
                    'CardType': card.card_type,
                    'Number': int(card.number),
                    'SecurityCode': int(card.cvv),
                    'PostalCode': int(card.zip)
                }
            ]
        elif giftcards:
            self.data['Payments'] = [{
                'Type': 'GiftCard',
                'Amount': giftcard.amount,
                'Number': giftcard.number,
                'SecurityCode': giftcard.pin,
            } for giftcard in giftcards]
            # Make sure our payments cover the entire purchase price
            # assert sum([float(p['Amount']) for p in self.data['Payments']]) == float(self.data['Amounts'].get('Customer', 0))
        else:
            self.data['Payments'] = [
                {
                    'Type': 'Cash',
                }
            ]

        return response
