'''
Signals and handlers for the aplication.
'''

from django.dispatch.dispatcher import receiver, Signal
import uuid
import threading
import logging

logger = logging.getLogger('django')

from django.template.loader import render_to_string
from django.core.mail import send_mass_mail
from open_facebook.exceptions import PermissionException
from django.conf import settings
import json

import client
import open_facebook

auction_started_signal = Signal(providing_args=["auction"])
auction_finished_signal = Signal(providing_args=["auction"])
precap_finished_signal = Signal(providing_args=["auction"])

task_auction_start = Signal(providing_args=["auction"])
task_auction_pause = Signal(providing_args=["auction"])


@receiver(auction_finished_signal)
def send_win_email(sender, **kwargs):
    try:
        client.send_pubnub_message(json.dumps({'method': 'log', 'params': 'SERVER: auction_finished_signal'}),
                                   '/topic/main/')
        logger.debug("Sending mail")
        auction = kwargs['auction']
        user = auction.winner

        if user and auction.bid_type == 'bid':
            print "sending email"

            from django.core.mail import EmailMultiAlternatives
            from django.template.loader import render_to_string
            from django.utils.html import strip_tags

            subject = render_to_string('bidding/auction_won_subject.txt',
                                       {'user': user,
                                        'item': auction.item}).replace('\n', '')
            from_email = settings.DEFAULT_FROM_EMAIL
            to = user.email

            html_content = render_to_string('bidding/mail_winner.html',
                                            {'user': user,
                                             'auction': auction,
                                             'site': settings.SITE_NAME,
                                             'images_site': settings.IMAGES_SITE})
            text_content = strip_tags(html_content) # this strips the html, so people will have the text as well.

            # create the email, and attach the HTML version as well.
            msg = EmailMultiAlternatives(subject, text_content, from_email, [to])
            msg.attach_alternative(html_content, "text/html")
            msg.send()

    except Exception:
        logging.info('signal.send_win_email', exc_info=True)
        raise


@receiver(auction_finished_signal)
def make_auction_invoice(sender, **kwargs):
    auction = kwargs['auction']
    client.send_pubnub_message(json.dumps({'method': 'log', 'params': 'SERVER: auction_finished_signal'}),
                               '/topic/main/')

    if auction.winner:

        from bidding.models import AuctionInvoice

        invoice = AuctionInvoice()
        invoice.auction = auction
        invoice.member = auction.winner.get_profile()
        invoice.uid = uuid.uuid4()
        invoice.save()

        #winnner for fun earns retail price in tokens!
        if auction.bid_type == 'token':
            mem = auction.winner.get_profile()
            mem.tokens_left += int(auction.item.retail_price)
            mem.save()

            client.callReverse(mem.facebook_id, 'reloadTokens')


#@receiver(precap_finished_signal)
def send_start_email(sender, **kwargs):
    client.send_pubnub_message(json.dumps({'method': 'log', 'params': 'SERVER: precap_finished_signal'}),
                               '/topic/main/')
    auction = kwargs['auction']

    user_mails = auction.bidder_mails()

    subject = render_to_string('bidding/auction_start_subject.txt',
                               {'item': auction.item}).replace('\n', '')

    message = render_to_string('bidding/auction_start_email.txt',
                               {'auction': auction,
                                'site': settings.SITE_NAME})

    data_tuples = []
    for mail in user_mails:
        data_tuples.append((subject, message, settings.DEFAULT_FROM_EMAIL, [mail]))

    send_mass_mail(data_tuples)


@receiver(auction_finished_signal)
def post_win_wall(sender, **kwargs):
    auction = kwargs['auction']
    logger.debug("Auction: %s" % auction)
    if auction.winner:
        member = auction.winner.get_profile()
        if auction.bid_type == 'token':
            msg = u'{name} has won this virtual item playing for tokens. If {name} had played for items he/she could have purchased it for {price} dollars!'
        else:
            msg = u'{name} can purchase {item} for {price} dollars!'
        link = settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME)

        args = {'caption': u'Auction won - {item}'.format(item=auction.item.name),
                'message': msg.format(name=member.user.first_name,
                                      item=auction.item.name,
                                      price=auction.won_price),
                'picture': auction.item.get_thumbnail(),
                'link': link,
        }
        try:
            member.post_to_wall(**args)
        except PermissionException:
            logger.debug('User forbid wallpost')
        except:
            raise

@receiver(auction_started_signal)
def notify_bidders(sender, **kwargs):
    auction = kwargs['auction']
    text = u'The auction for a {item} has started. Hurry and go win it!.'.format(item=auction.item.name)
    for member in auction.bidders.all():
        of = open_facebook.OpenFacebook(member.access_token)
        args = {'template': text,
            'access_token': open_facebook.FacebookAuthorization.get_app_access_token()}
        logger.debug("Notification - ARGS: %s" % args)
        destination = '{facebook_id}/notifications'.format(facebook_id=member.facebook_id)
        response = of.set(destination, **args)

def send_in_thread(signal, **kwargs):
    """ 
    Sends the given signal in a different thread, so it doesn't delay further
    actions.
    """
    ## to disable thread uncomment this
    #signal.send(**kwargs)

    th = threading.Thread(target=signal.send, kwargs=kwargs)
    th.start()

