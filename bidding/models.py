# -*- coding: utf-8 -*-

import time
import re
import json
import threading
from datetime import datetime, timedelta
from decimal import Decimal
from urllib2 import urlopen

import open_facebook
import django.dispatch
from django.conf import settings
from django.contrib.auth.models import AbstractUser, UserManager
from django.core.urlresolvers import reverse
from django.db import models
from django.db.models.aggregates import Sum
from django.db.models.signals import post_save
from django.dispatch.dispatcher import receiver
from django.utils.safestring import mark_safe
from django_facebook.models import FacebookModel
from sorl.thumbnail import get_thumbnail

import logging
logger = logging.getLogger('django')

from apps.audit.models import AuditedModel
from bidding import client
from chat import auctioneer
from bidding.signals import auction_finished_signal
from bidding.signals import auction_started_signal
from bidding.signals import precap_finished_signal
from bidding.signals import precap_finishing_signal
from bidding.signals import task_auction_pause
from bidding.signals import send_in_thread
from lib import metrics


metrics.initialize(settings.MIXPANEL_TOKEN)
re_bids = re.compile("(\d+)")


AUCTION_STATUS_CHOICES = (
    ('precap', 'Pre-Capitalization'),
    ('waiting', 'Waiting start date'),
    ('processing', 'In Process'),
    ('pause', 'Paused'),
    ('waiting_payment', 'Waiting Payment'),
    ('paid', 'Paid'),
)

ITEM_CATEGORY_CHOICES = (
    ('elec', 'Electronics'),
    ('fash', 'Fashion'),
    ('moto', 'Motors'),
    ('ente', 'Entertainment'),
    ('deal', 'Deals & gifts'),
    ('home', 'Home & outdoors'),
    ('oth', 'Other'),
)

INVOICE_CHOICES = (
    ('created', 'Created'),
    ('paid', 'Paid'),
    ('canceled', 'Canceled'),
)

PAYMENT_CHOICES = (
    ('direct', 'Direct'),
    ('express', 'Express'),
)

BID_TYPE_CHOICES = (
    ('bid', 'Bids'),
    ('token', 'Tokens'),
    ('bidsto', 'Bidsto')
)



class Google_profile(models.Model):
    
    profile_url =  models.URLField(null=True,blank=True,max_length=255)
    profile_picture_url = models.URLField(null=True,blank=True,max_length=255)
    displayName = models.CharField(null=True,blank=True,max_length=255)
    email = models.EmailField(null=True,blank=True,max_length=255)
    gender = models.CharField(null=True,blank=True,max_length=255)
    user = models.ForeignKey(settings.AUTH_USER_MODEL, related_name='google_profile')
    
class Member(AbstractUser, FacebookModel):
    objects = UserManager()

    bids_left = models.IntegerField(default=0)
    tokens_left = models.IntegerField(default=0)
    bidsto_left = models.IntegerField(default=0)

    session = models.TextField(default='{}')

    remove_from_chat = models.BooleanField(default=False)

    #not the prettiest but ok
    def get_bids(self, bid_type):
        """ Returns the member bids of the given type. """
        if bid_type == 'token':
            return self.tokens_left
        else:
            return self.bidsto_left + self.bids_left

    def get_bids_left(self):
        return self.get_bids('bid')

    def get_tokens_left(self):
        return self.get_bids('token')

    def set_bids(self, bid_type, amount):
        """ Sets the member bids of the given type. """
        if bid_type == 'token':
            self.tokens_left = amount
        else:
            # We first decrease bidsto
            if self.bidsto_left:
                diff = self.get_bids_left() - amount
                if self.bidsto_left >= diff:
                    self.bidsto_left -= diff
                else:
                    diff -= self.bidsto_left
                    self.bidsto_left = 0
                    self.bids_left -= diff
            else:
                self.bids_left = amount

    def maximun_bids_from_tokens(self):
        return int(self.tokens_left * settings.TOKENS_TO_BIDS_RATE)

    def get_active_auctions(self):
        return self.auction_set.filter(is_active=True).count()

    def gen_available_tokens_to_bids(self):
        NUMS = (1, 2, 5)
        n = 1
        availables = []
        maximun = self.maximun_bids_from_tokens()
        while (n * NUMS[0] < maximun):
            availables += [d * n for d in NUMS if d * n <= maximun]
            n *= 10
        if maximun not in availables:
            availables.append(maximun)
        return availables

    def auction_bids_left(self, auction):
        """
        Return the amount of unused commited bids the member has for the
        given auction.
        """

        bid = self.bid_set.filter(auction=auction)
        return bid[0].left() if bid else 0

    def precap_bids(self, auction, amount):
        """
        Creates the specified amount of precap bids for the user in the given
        auction. Updates the member accordingly.
        """

        unixtime = Decimal("%f" % time.time())
        bid, _ = Bid.objects.get_or_create(auction=auction, bidder=self, defaults={'unixtime': unixtime})

        diff = amount - bid.placed_amount

        bid.time = unixtime
        bid.placed_amount = amount
        bid.save()
        auction.save()

        #self.bids_left -= diff
        self.set_bids(auction.bid_type, self.get_bids(auction.bid_type) - diff)
        self.save()

    def get_placed_amount(self, auction):
        """
        Creates the specified amount of precap bids for the user in the given
        auction. Updates the member accordingly.
        """

        unixtime = Decimal("%f" % time.time())
        bid, _ = Bid.objects.get_or_create(auction=auction, bidder=self, defaults={'unixtime': unixtime})

        return bid.placed_amount

    def leave_auction(self, auction):
        """ Retires the member bids from the given auction. """
        try:
            # TODO: This should be removed as is not going to be used
            bids = Bid.objects.get(auction=auction, bidder=self)
            #self.bids_left += bids.placed_amount
            self.set_bids(auction.bid_type, self.get_bids(auction.bid_type) +
                                            bids.placed_amount)
            bids.delete()
            self.save()
        except:
            logger.exception('leave_auction exception')

    def bids_history(self):
        return self.bid_set.all().order_by().values('auction__item__name', 'placed_amount', 'used_amount',
                                                    'auction__bid_type')

    def display_name(self):
        return "%s %s" % (self.first_name,
                          self.last_name)

    def display_linked_facebook_profile(self):
        output = ""
        if self.facebook_profile_url:
            output = '<a href="%s">' % self.facebook_profile_url
        output += self.display_name()
        if self.facebook_profile_url:
            output += '</a>'
        return mark_safe(output)

    def display_picture(self):
        
        if self.facebook_id:
            return "https://graph.facebook.com/%s/picture" % self.facebook_id
        else:
            if self.google_profile.count() > 0:
                return self.google_profile.all()[0].profile_picture_url
            return ""

    def can_chat(self, auction_id):
        """ Returns True if the user can chat in the given auction. """
        auction = Auction.objects.get(id=auction_id)
        return not self.remove_from_chat and auction.has_joined(self)

    def post_win_story(self, **args):
        """ Posts a story when winning an item in an auction."""
        of = open_facebook.OpenFacebook(self.access_token)
        response = of.set('me/{app}:win'.format(app=settings.FACEBOOK_APP_NAME), **args)

    def fb_check_like(self):
        ''' Checks if user likes the app in facebook '''
        of = open_facebook.OpenFacebook(self.access_token)
        response = of.get('me/og.likes',)
        return response

    def fb_like(self):
        ''' User like the app in facebook '''
        of = open_facebook.OpenFacebook(self.access_token)
        response = of.set('me/og.likes', {'object': settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME), })
        logger.debug('Response: %s' % response)

    def send_notification(self, message):
        of = open_facebook.OpenFacebook(self.access_token)
        of.set('me/apprequests', message=message)

    def post_facebook_registration(self, request):
        '''
        Behaviour after registering with facebook
        '''
        from django_facebook.utils import next_redirect

        default_url = reverse('facebook_connect')
        response = next_redirect(request, default=default_url, next_key='register_next')

        return response

    def getSession(self, key=None, default=None):
        if not key:
            if self.session:
                ss = json.loads(self.session)
                if type(ss) is not dict:
                    ss = {}
            else:
                ss = {}
            return ss
        elif type(key) is str:
            ss = self.getSession()
            if key in ss:
                return ss[key]
            else:
                return default
        else:
            raise Exception('key param is not str')

    def setSession(self, sessionDict, sessionValue=None):
        if not sessionValue and type(sessionDict) is dict:
            #just dump the dict into session
            self.session = json.dumps(sessionDict)
        elif type(sessionDict) is str:
            #set the key value
            s = self.getSession()
            s[sessionDict] = sessionValue
            self.session = json.dumps(s)
            self.save()

    def delSession(self, key):
        s = self.getSession()
        if key in s:
            del s[key]
            self.session = json.dumps(s)
            self.save()

    def __unicode__(self):
        return self.username


class Category(models.Model):
    name = models.CharField(max_length=55)
    description = models.TextField()
    image = models.ImageField(upload_to='item_category/', blank=True, null=True)

    def __unicode__(self):
        return self.name

    def get_thumbnail(self, size='107x72'):
        if self.image:
            return settings.IMAGES_SITE + get_thumbnail(self.image.name, size).url
        return None


class Item(AuditedModel):
    name = models.CharField(max_length=255)
    slug = models.SlugField(unique=True, help_text='Used to identify the item, should be unique')
    retail_price = models.DecimalField(max_digits=10, decimal_places=2)
    total_price = models.DecimalField(max_digits=10, decimal_places=2, blank=True, null=True)
    description = models.TextField()
    specification = models.TextField(blank=True, null=True)
    categories = models.ManyToManyField(Category, related_name="items", blank=True, null=True)
    name.alphabetic_filter = True

    def get_thumbnail(self, size='107x72'):
        qs = self.itemimage_set.all()
        if qs:
            return settings.IMAGES_SITE + get_thumbnail(qs[0].image.name, size).url
        return None


    def __unicode__(self):
        return self.name


class ItemImage(models.Model):
    item = models.ForeignKey(Item)
    image = models.ImageField(upload_to='items/')


class AbstractAuction(AuditedModel):
    item = models.ForeignKey(Item)
    precap_bids = models.IntegerField(help_text='Minimum amount of bids to start the auction')
    minimum_precap = models.IntegerField(help_text='This is the bidPrice', default=10)

    class Meta:
        abstract = True


class Auction(AbstractAuction):
    bid_type = models.CharField(max_length=5, choices=BID_TYPE_CHOICES, default='bid', help_text='Type of currency for this auction.')
    status = models.CharField(max_length=15, choices=AUCTION_STATUS_CHOICES, default='precap', help_text='Auction status.')
    bidding_time = models.IntegerField(default=10, help_text='Auction initial timer')
    saved_time = models.IntegerField(default=0, blank=True, null=True, help_text='Saved bidding time for later use.')
    finish_time = models.IntegerField(default=0, blank=True, null=True)
    always_alive = models.BooleanField(default=False, help_text='Wether the auction copies itself after precap.')
    bidders = models.ManyToManyField(Member, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    priority = models.IntegerField(default=-1, help_text='Used for sorting.')
    categories = models.ManyToManyField(Category,related_name="auctions",blank=True, null=True)
    
    #winner info
    winner = models.ForeignKey(Member, related_name='autcions', blank=True, null=True)
    won_date = models.DateTimeField(null=True, blank=True)
    won_price = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)

    #scheduling options
    start_date = models.DateTimeField(help_text='Date and time the auction is scheduled to start',
                                      null=True, blank=True)
    start_time = models.TimeField(help_text='Time of day the auction is scheduled to start',
                                      null=True, blank=True)

    #treshold
    threshold1 = models.IntegerField('25% Threshold',
                                     help_text='Bidding time after using 25% of commited bids. Will be ignored if blank.',
                                     null=True, blank=True, default=7)
    threshold2 = models.IntegerField('50% Threshold',
                                     help_text='Bidding time after using 50% of commited bids. Will be ignored if blank.',
                                     null=True, blank=True, default=5)
    threshold3 = models.IntegerField('75% Threshold',
                                     help_text='Bidding time after using 75% of commited bids. Will be ignored if blank.',
                                     null=True, blank=True, default=3)

    class Meta:
        ordering = ['-id']

    def save(self, *args, **kwargs):
        if self.start_date:
            self.start_date = self.start_date.replace(second=0, microsecond = 0)
        super(Auction, self).save()

    def placed_bids(self):
        """ Returns the amount of bids commited in precap. """
        return self.bid_set.aggregate(Sum('placed_amount'))['placed_amount__sum'] or 0

    def used_bids(self):
        """ Returns the amount of precap bids already used in the auction. """
        return self.bid_set.aggregate(Sum('used_amount'))['used_amount__sum'] or 0

    def price(self):
        """ Returns the current price of the auction. """
        dollars = float(self.used_bids() / self.minimum_precap) / 100
        return Decimal('%.2f' % dollars)

    def has_joined(self, member):
        """ Returns True if the member has joined the auction. """
        return member in self.bidders.all()

    def bidder_mails(self):
        """ Returns a list of mails of members that have joined this auction. """
        return self.bidders.values_list('user__email', flat=True)

    def getBidNumber(self):
        return self.used_bids() / self.minimum_precap

    def __unicode__(self):
        return u'%s - %s' % (self.item.name, self.get_status_display())

    def start_auction(self):
        #refresh the current database auction status
       
        bid_number = 0
        if self.status == 'waiting':
            self.start()
        elif self.status == 'pause':
            self.resume()
        self.finish_auction_delayed(self.getBidNumber(), self.bidding_time)
    
    def start(self):
        if self.status == 'waiting':
            """ Starts the auction and saves the model. """
            self.status = 'processing'
            client.auctionActive(self)
            self.saved_time = self.bidding_time
            self.save()
            send_in_thread(auction_started_signal, sender=self)
        
    def finish_auction(self, bid_number):
        #refresh the current database auction status
        if self.status == 'processing' and bid_number == self.getBidNumber():
            self.finish()
        else:
            self.save()

    def start_auction_delayed(self, delay):
        t = threading.Timer(delay, self.start_auction)
        t.start()
    
    def finish_auction_delayed(self, bid_number, delay):
        kwargs = {'bid_number': bid_number}
        t = threading.Timer(delay, self.finish_auction, kwargs=kwargs)
        t.start()

    def get_last_bidder(self):
        """
        Returns the username of the last member that placed a bid on this
        auction.
        """
        qs = self.bid_set.order_by('-unixtime')

        if not qs or not qs[0].used_amount > 0:
            return None

        return qs[0].bidder

    def get_latest_bid(self):
        """
        Returns the most recent bid of the auction.
        """
        bid_query = self.bid_set.order_by('-unixtime')
        return bid_query[0] if bid_query else None

    def can_precap(self, member, amount):
        """
        Returns True if the member can place the specified amount of precap
        bids in this auction.
        """
        if self.status == 'precap':
            return member.get_bids(self.bid_type) + member.get_placed_amount(self) >= amount
        elif self.status == 'waiting':
            return (member.get_bids(self.bid_type) >= amount
                and not self.has_joined(member))
        return None

    def completion(self, n=0):
        """ Returns a completion percentaje (0-100 integer) of the precap. """
        if self.status == 'precap':
            percentaje = int((self.placed_bids() * 100) / self.precap_bids)
            if n != 0:
                """ Returns percentaje without n bids """
                bids = self.placed_bids() - (n * self.minimum_precap)
                percentaje = int((bids * 100) / self.precap_bids)
            return percentaje
        return 100

    def get_time_left(self):
        time_left = None
        if self.status == 'waiting':
            time_left = self.start_date - datetime.utcnow()
            time_left = (time_left.microseconds + (time_left.seconds + time_left.days * 24 * 3600) * 10**6) / 10**6
        elif self.status == 'processing':
            bid = self.get_latest_bid()
            if bid:
                if bid.used_amount == 0:
                    time_left = float(self.finish_time) - time.time()
                else:
                    time_left = (float(self.bidding_time) - time.time() + float(bid.unixtime))
        if time_left:
            return round(time_left) if time_left > 0 else 0
        return None

    def _precap_bids_needed(self):
            """
            Returns the amount of bids needed before the precap is finished.
            """
            needed = self.precap_bids - self.placed_bids()
            return needed if needed > 0 else 0

    def can_bid(self, member):
        """
        Returns True if the member has commited bids left to use on the
        auction, and its not the last bidder.
        """
        if self.get_last_bidder() == member:
            return False
        return member.auction_bids_left(self)
  
    def place_precap_bid(self, member, amount, add = True):

        if self.status == 'precap':
            """
            The member commits an amount precap bid to the auction and saves its
            state.
            Checks if the auction precap should be finished.
            Returns True if the member just joined the auction.
            """
            joining = not self.has_joined(member)
            if joining:
                self.bidders.add(member)
            member.precap_bids(self, amount)
            if add :
                if self.bid_type == 'bid':
                    notification_percentage = ConfigKey.get('NOTIFICATION_CREDIT_PERCENTAGE', 90)
                elif self.bid_type == 'token':
                    notification_percentage = ConfigKey.get('NOTIFICATION_TOKEN_PERCENTAGE', 90)
                else:
                    notification_percentage = 0
                previous_finishing = self.completion(1) < notification_percentage
                if self.completion() >= notification_percentage > 0 and previous_finishing == True:
                    send_in_thread(precap_finishing_signal, sender=self)

            #TODO two users can enter here because status is not yet changed
            if not self._precap_bids_needed():
                self.finish_precap()
            return joining

        elif self.status == 'waiting':
            """
            The member joins the auction. No validations are made (can_precap
            is assumed to be True).
            """
            self.bidders.add(member)
            member.precap_bids(self, amount)
            return True

    def leave_auction(self, member):
        """ Returns all the bids commited to the auction by the member. """

        self.bidders.remove(member)
        member.leave_auction(self)

    def _check_preload_auctions(self):
        """
        Checks the amount of upcoming auctions, and runs a fixture in case
        there are not enough.
        """
        upcoming = Auction.objects.filter(bid_type=self.bid_type,
                                          is_active=True, status__in='precap').count()

        for fixture in AuctionFixture.objects.filter(
                bid_type=self.bid_type,
                automatic=True):
            if fixture.threshold > upcoming:
                fixture.make_auctions()

    def finish_precap(self):
        """
        Changes the status to Waiting, sets the auction start date and saves
        it.
        """
        self.status = 'waiting'
        if self.bid_type == 'bid':
            now = datetime.utcnow().replace(second=0, microsecond=0)
            if not self.start_time:
                self.start_time = datetime.utcnow() + timedelta(seconds=5)
            self.start_date = now.replace(hour=self.start_time.hour, minute=self.start_time.minute) + timedelta(days=1)
            #time.mktime(time.strptime(str(self.start_date),'%Y-%m-%d %H:%M:%S'))
        elif self.bid_type == 'token':
            self.start_date = datetime.utcnow() + timedelta(seconds=5)
        self.finish_time = 0 
        self.save()
        if self.always_alive:
            auction_copy = Auction.objects.create(item=self.item,
                                                  bid_type=self.bid_type,
                                                  precap_bids=self.precap_bids,
                                                  minimum_precap=self.minimum_precap,
                                                  is_active=self.is_active,
                                                  always_alive=self.always_alive,
                                                  bidding_time=self.bidding_time,
                                                  threshold1=self.threshold1,
                                                  threshold2=self.threshold2,
                                                  threshold3=self.threshold3,
                                                  priority=self.priority,
                                                  finish_time=self.finish_time,
                                                  start_time=self.start_time)
            auction_copy.save()

        auctioneer.precap_finished_message(self)
        client.auctionAwait(self)
        if self.bid_type == 'bid':
            send_in_thread(precap_finished_signal, sender=self)
        elif self.bid_type == 'token':
            logger.debug('starting auction keeper')
            keeper = AuctionKeeper()
            keeper.auction_id = self.id
            keeper.start()

    def start(self):
        """ Starts the auction and saves the model. """
        self.status = 'processing'
        self.saved_time = self.bidding_time
        self.finish_time = time.time() + self.bidding_time
        self.save()

        client.auctionActive(self)
        send_in_thread(auction_started_signal, sender=self)

    def bid(self, member, bidNumber):
        """
        Uses one of the member's commited bids in the auction.
        """
        bid = self.bid_set.get(bidder=member)
        bid.used_amount += self.minimum_precap
        bid_time = time.time()
        bid.unixtime = Decimal("%f" % bid_time)
        bid.save()

        if self._check_thresholds():
            self.pause(15.0)
        else:
            self.finish_time = time.time() + self.bidding_time
            self.save()
        return bid

    def pause(self, delay):
        """ pauses the auction. """
        self.status = 'pause'
        self.finish_time = time.time() + delay
        self.save()
        client.auctionPause(self)
        send_in_thread(task_auction_pause, sender=self)

    def resume(self):
        """ Resumes the auction. """
        self.status = 'processing'
        self.finish_time = time.time() + self.bidding_time
        self.save()

        #fixme ugly
        bid = self.get_latest_bid()
        now = time.time()
        bid.unixtime = Decimal("%f" % now)
        bid.save()

        client.auctionResume(self)

    def finish(self):
        """ Marks the auction as finished, sets the winner and win time. """
        bidder = self.get_last_bidder()
        self.winner = bidder if bidder else None
        self.won_price = self.price()
        self.status = 'waiting_payment'
        self.won_date = datetime.now()
        self.save()
        if self.winner is not None:
            metrics.win_auction(self.winner, self)
        auctioneer.auction_finished_message(self)
        client.auctionFinish(self)
        send_in_thread(auction_finished_signal, sender=self)

    def _check_thresholds(self):
        """
        Checks if a threshold has been reached, and modifies the bidding time
        accordingly. If a threshold is reached True is returned.
        """
        current_bids = self.used_bids()
        limt_bids = int(self.placed_bids() * 0.25)

        while limt_bids % self.minimum_precap != 0:
            limt_bids -= 1

        if self.threshold1 and current_bids == limt_bids:
            self.bidding_time = self.threshold1
            auctioneer.threshold_message(auction=self, number=1)
            return True
        if self.threshold2 and current_bids == 2 * limt_bids:
            self.bidding_time = self.threshold2
            auctioneer.threshold_message(auction=self, number=2)
            return True
        if self.threshold3 and current_bids == 3 * limt_bids:
            self.bidding_time = self.threshold3
            auctioneer.threshold_message(auction=self, number=3)
            return True
        return False
     
@receiver(post_save, sender=Auction)
def categories_register(sender, instance, **kwargs):
    if not instance.categories.count() > 0 and instance.item.categories.count() > 0:
        [instance.categories.add(x) for x in instance.item.categories.all()]
        instance.save()

#class PrePromotedAuction(AbstractAuction):
#    bid_type = models.CharField(max_length=5, choices=BID_TYPE_CHOICES, default='bid')
#    status = models.CharField(max_length=15, choices=AUCTION_STATUS_CHOICES, default='precap')
#    bidding_time = models.IntegerField(default=10)
#    saved_time = models.IntegerField(default=0, blank=True, null=True)
#
#    #treshold
#    threshold1 = models.IntegerField('25% Threshold',
#                                     help_text='Bidding time after using 25% of commited bids. Will be ignored if blank.',
#                                     null=True, blank=True, default=12)
#    threshold2 = models.IntegerField('50% Threshold',
#                                     help_text='Bidding time after using 50% of commited bids. Will be ignored if blank.',
#                                     null=True, blank=True, default=8)
#    threshold3 = models.IntegerField('75% Threshold',
#                                     help_text='Bidding time after using 75% of commited bids. Will be ignored if blank.',
#                                     null=True, blank=True, default=5)
#
#    is_active = models.BooleanField(default=True)
#
#    class Meta:
#        ordering = ['-id']
#
#    def _state_delegate(self):
#        return state_delegates[self.status](self)
#
#    def __getattr__(self, name):
#        """ Tries to forward non resolved calls to the delegate objects. """
#        logger.debug("Name: %s" % name)
#        sd = self._state_delegate()
#        if hasattr(sd, name):
#            return getattr(sd, name)
#
#        if hasattr(super(PrePromotedAuction, self), '__getattr__'):
#            return super(PrePromotedAuction, self).__getattr__(name)
#        else:
#            raise AttributeError
#
#
#    def placed_bids(self):
#        """ Returns the amount of bids commited in precap. """
#        return self.bid_set.aggregate(Sum('placed_amount')
#        )['placed_amount__sum'] or 0
#
#    def used_bids(self):
#        """ Returns the amount of precap bids already used in the auction. """
#        return self.bid_set.aggregate(Sum('used_amount')
#        )['used_amount__sum'] or 0
#
#    def price(self):
#        """ Returns the current price of the auction. """
#
#        dollars = float(self.used_bids()) / 100
#        return Decimal('%.2f' % dollars)
#
#    def has_joined(self, member):
#        """ Returns True if the member has joined the auction. """
#
#        return member in self.bidders.all()
#
#    def bidder_mails(self):
#        """ Returns a list of mails of members that have joined this auction. """
#
#        return self.bidders.values_list('user__email', flat=True)
#
#    def __unicode__(self):
#        return u'%s - %s' % (self.item.name, self.get_status_display())
#

class PromotedAuction(Auction):
    promoter = models.ForeignKey(Member, blank=False, null=False, related_name="promoter_user")


class Bid(AuditedModel):
    auction = models.ForeignKey(Auction)
    bidder = models.ForeignKey(Member)

    #why unix time and not date?
    unixtime = models.DecimalField(max_digits=17, decimal_places=5, db_index=True)

    #Created on precap. Marked as used when is placed during the auction.
    placed_amount = models.IntegerField(default=0)
    used_amount = models.IntegerField(default=0)

    def left(self):
        """ Returns the amount of placed bids that haven't been used. """

        return self.placed_amount - self.used_amount

    class Meta:
        unique_together = ('auction', 'bidder')


class BidPackage(models.Model):
    title = models.CharField(max_length=55)
    description = models.TextField()
    price = models.IntegerField()
    bids = models.IntegerField(default=0)
    apple_store_key = models.CharField(max_length=55)
    image = models.ImageField(upload_to='bid_packages/', blank=True, null=True)

    def __unicode__(self):
        return self.title


@receiver(post_save, sender=BidPackage)
def update_fb_info(sender, instance, **kwargs):
    url = 'https://graph.facebook.com/?id=%s&scrape=true&method=post' % (settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME) + 'bid_package/' + str(instance.id))
    urlopen(url)


class AuctionInvoice(AuditedModel):
    auction = models.ForeignKey(Auction)
    member = models.ForeignKey(Member)
    status = models.CharField(max_length=55, default='created', choices=INVOICE_CHOICES)
    payment = models.CharField(max_length=55, default='direct', choices=PAYMENT_CHOICES)
    uid = models.CharField(max_length=40, db_index=True)
    created = models.DateTimeField(default=datetime.now)


from paypal.standard.ipn.signals import payment_was_successful


#def addbids(sender, **kwargs):
##TODO move to signals.py?
#    ipn_obj = sender
#    if ipn_obj.custom.startswith('item'):
#        invoice = AuctionInvoice.objects.get(uid=ipn_obj.invoice)
#        auction = invoice.auction
#        auction.status = 'paid'
#        auction.save()
#        invoice.status = 'paid'
#        invoice.save()
#        #TODO maybe pay method in auction. And delete bid objects there
#payment_was_successful.connect(addbids)


class Invitation(AuditedModel):
    inviter = models.ForeignKey(Member)
    invited_facebook_id = models.CharField(max_length=100)
    deleted = models.BooleanField(default=False)  # facebook forced you to remove the invitation once used but not anymore


class AuctionInvitation(models.Model):
    """DEPRECATED"""
    inviter = models.ForeignKey(Member)
    request_id = models.BigIntegerField()
    auction = models.ForeignKey(Auction)

    def delete_facebook_request(self, member):
        """ Deletes the user request from the facebook profile. """
        of = open_facebook.OpenFacebook(member.access_token)
        of.delete('{request_id}_{user_id}'.format(request_id=self.request_id,
                                                  user_id=member.facebook_id))


class ConvertHistory(models.Model):
    member = models.ForeignKey(Member)
    tokens_amount = models.IntegerField(null=True, default=0)
    bids_amount = models.IntegerField(null=True, default=0)
    total_tokens = models.IntegerField(default=0)
    total_bids = models.IntegerField(default=0)
    total_bidsto = models.IntegerField(default=0)
    date = models.DateTimeField(auto_now=True)

    @staticmethod
    def convert(member, num_bids):
        tokens_amount = (num_bids / settings.TOKENS_TO_BIDS_RATE)

        if member.tokens_left >= tokens_amount:
            #TODO: add bidsto
            #member.bidsto_left += num_bids
            member.bids_left += num_bids
            member.tokens_left -= tokens_amount
            member.save()

        ConvertHistory.objects.create(member=member,
                                      tokens_amount=tokens_amount,
                                      bids_amount=num_bids,
                                      total_tokens=member.tokens_left,
                                      total_bids=member.bids_left,
                                      total_bidsto=member.bidsto_left,
        )
FB_STATUS_CHOICES = (
                     ('confirmed', 'confirmed'),
)


class FBOrderInfo(AuditedModel):
    member = models.ForeignKey(Member)
    package = models.ForeignKey(BidPackage)
    status = models.CharField(choices=FB_STATUS_CHOICES, max_length=25)
    fb_payment_id = models.BigIntegerField(blank=True, null=True)  # this field should be unique
    date = models.DateTimeField(auto_now_add=True, null=True)


    def __unicode__(self):
        return repr(self.member) + ' -> ' + repr(self.package) + ' (' + self.status + ')'



class IOPaymentInfo(AuditedModel):
    member = models.ForeignKey(Member)
    package = models.ForeignKey(BidPackage, null=True)
    transaction_id = models.CharField(max_length=255,unique=True)  # this field should be unique
    quantity = models.IntegerField()
    purchase_date = models.DateTimeField(null=True)

    def __unicode__(self):
        return repr(self.member) + ' - ' + repr(self.package) + ' (' + str(self.purchase_date) + ')'

class PaypalPaymentInfo(AuditedModel):
    member = models.ForeignKey(Member)
    package = models.ForeignKey(BidPackage, null=True)
    transaction_id = models.CharField(max_length=19, help_text="PayPal transaction ID.", db_index=True, unique=True)  # this field should be unique
    quantity = models.IntegerField()
    purchase_date = models.DateTimeField(null=True)

    def __unicode__(self):
        return repr(self.member) + ' - ' + repr(self.package) + ' (' + str(self.purchase_date) + ')'


#@receiver(post_save, sender=FBOrderInfo)
#@receiver(post_save, sender=IOPaymentInfo)
buy_tokens = django.dispatch.Signal(providing_args=["instance"])
def on_confirmed_order(sender,**kwargs):
    """Function to add order to the history when confirmed"""
    #if instance.status == 'confirmed':
    instance=kwargs['instance']
    ConvertHistory.objects.create(member=instance.member,
                                  tokens_amount=0,
                                  bids_amount=instance.package.bids,
                                  total_tokens=instance.member.tokens_left,
                                  total_bids=instance.member.bids_left,
                                  total_bidsto=instance.member.bidsto_left,
    )
buy_tokens.connect(on_confirmed_order)


CONFIG_KEY_TYPES = (('text', 'text'),
                    ('int', 'int'),
                    ('boolean', 'boolean'))


class ConfigKey(models.Model):
    key = models.CharField(max_length=100)
    value = models.TextField()
    description = models.TextField(null=True, blank=True)
    value_type = models.CharField(choices=CONFIG_KEY_TYPES, null=False, blank=False, max_length=10, default='text')

    @staticmethod

    def get(key, default=None, default_type=None, default_description=None):
        result = ConfigKey.objects.filter(key=key).all()
        if len(result):
            result = result[0]
            try:
                #velidate the type
                if result.value_type == 'text':
                    return str(result.value)
                elif result.value_type == 'int':
                    return int(result.value)
                elif result.value_type == 'boolean':
                    if result.value.lower() in ('yes', 'si', 'true', 'verdad', 'verdadero'):
                        return True
                    else:
                        return False
                else:
                    return result.value
            except:
                return default
        else:
            new_config_key = ConfigKey.objects.create(key=key, value=default, description=default_description)
            if default_type:
                default_value_type = default_type
            else:
                default_value_type = type(default)
            if default_value_type is int or default_value_type is long:
                new_config_key.value_type = 'int'
            elif default_value_type is bool:
                new_config_key.value_type = 'boolean'
            elif default_value_type is str:
                new_config_key.value_type = 'text'
            new_config_key.save()
            return new_config_key.value

    def __unicode__(self):
        return self.key


class AuctionKeeper(threading.Thread):
    def __init__(self, *args, **kwargs):
        super(AuctionKeeper, self).__init__(*args, **kwargs)
        self.auction_id = None
        self.check_delay = 1

    def run(self):
        stop = False
        while not stop:
            time.sleep(self.check_delay)
            auction = Auction.objects.select_for_update().get(id=self.auction_id)
            if auction.finish_time <= time.time():
                if auction.status == 'processing':
                    auction.finish()
                    stop = True
                elif auction.status == 'waiting':
                    auction.start()
                elif auction.status == 'pause':
                    auction.resume()
                else:
                    logger.debug('Keeper: unknown auction status: %s' % auction.status)
                    stop = True
            auction.save()
