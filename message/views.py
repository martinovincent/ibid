# -*- coding: utf-8 -*-
# Create your views here.

from datetime import datetime
import time

from django.http import HttpResponse

from bidding.models import Auction, ConfigKey
from chat.models import Message
from models import EventLog

import message.value_objects as vo
import message.value_objects_factory as vo_factory


def message_listener(request):
    """api calls go through this method"""
    #process the in events
    returnEventList = listener(request)
    #process the out events
    return dispatcher(returnEventList)


def listener(request):
    """
    listener iters each in event and do the respective calls
    """
    #extract the events from the request
    eventList = vo_factory.create_voEventList(request)

    returnEventList = vo.EventList()

    for event in eventList:
        # save in events in eventLog
        EventLog().saveEvent(event)
        # check the class and method name
        splitEvent = event['event'].split(':')
        _class = splitEvent[0]
        method = splitEvent[1]
        data = event['data']
        # the method call itself
        #TODO: check how to call the method dinamically
        result = globals()[_class][method](request, data)
        returnEventList.extend(result)

    return returnEventList


def dispatcher(returnEventList):
    """
    dispatch each event through its defined transport
    """
    #define return lists for each transport
    returnEventList[vo.Event.TRANSPORT.REQUEST] = [event for event in returnEventList if event['transport']==vo.Event.TRANSPORT.REQUEST]
    returnEventList[vo.Event.TRANSPORT.PUBNUB] = [event for event in returnEventList if event['transport']==vo.Event.TRANSPORT.PUBNUB]

    # save out events in eventLog
    [EventLog().saveEvent(event) for event in returnEventList if event['transport']==vo.Event.TRANSPORT.PUBNUB]

    # TODO:send messages for pubnub transport
    #transport.pubnub(returnEventList[vo.Event.TRANSPORT.PUBNUB])

    # send messages for request transport
    return HttpResponse([event.toJson() for event in returnEventList[vo.Event.TRANSPORT.REQUEST]], content_type="application/json")


class bidding(object):
    @staticmethod
    def initialize(request, data):
        member = request.user.get_profile()

        eventList = vo.EventList()


        #################################
        ## event load user data        ##
        #################################

        event = vo.Event()
        event['event'] = vo.Event.EVENT.MAIN__LOAD_USER_DETAILS
        event['data'] = vo_factory.create_voLoggedInUser(member)
        event['sender'] = vo.Event.SENDER.SERVER
        event['receiver'] = vo.Event.RECEIVER.CLIENT_FB + str(member.facebook_id)
        event['transport'] = vo.Event.TRANSPORT.REQUEST
        event['timestamp'] = datetime.now()
        event['id'] = None

        eventList.append(event)


        #################################
        ## event load auctions         ##
        #################################

        my_auctions = Auction.objects.filter(is_active=True).exclude(status__in=('waiting_payment', 'paid')).order_by(
            '-status').filter(bidders=member)
        other_auctions = Auction.objects.filter(is_active=True).exclude(
            status__in=('waiting_payment', 'paid', 'waiting', 'processing', 'pause')).order_by('-status').exclude(
            bidders=member)
        finished_auctions = Auction.objects.filter(is_active=True, status__in=(
            'waiting_payment', 'paid', 'waiting', 'processing', 'pause')).filter(winner__isnull=False).order_by('-won_date')

        allAuctions = []
        allAuctions.extend(my_auctions)
        allAuctions.extend(other_auctions.filter(bid_type='bid')[:12])
        allAuctions.extend(other_auctions.filter(bid_type='token')[:12])
        allAuctions.extend(finished_auctions.filter(bid_type='bid')[:12])
        allAuctions.extend(finished_auctions.filter(bid_type='token')[:12])

        auctions = []

        for auct in allAuctions:
            auction = vo_factory.create_voAction(auct, member)

            if auction['mine'] and auction['status'] == 'processing':
                for mm in Message.objects.filter(auction=auct).filter(_user__isnull=True).order_by('-created')[:20]:
                    w = vo_factory.create_voAuctioneerMessage(mm)
                    auction['auctioneerMessages'].append(w)

                for mm in Message.objects.filter(auction=auct).filter(_user__isnull=False).order_by('-created')[:20]:
                    w = vo_factory.create_voMessage(mm)
                    auction['chatMessages'].insert(0, w)

            auctions.append(auction)

        event = vo.Event()
        event['event'] = vo.Event.EVENT.MAIN__LOAD_AUCTIONS
        event['data'] = auctions
        event['sender'] = vo.Event.SENDER.SERVER
        event['receiver'] = vo.Event.RECEIVER.CLIENT_FB + str(member.facebook_id)
        event['transport'] = vo.Event.TRANSPORT.REQUEST
        event['timestamp'] = datetime.now()
        event['id'] = None

        eventList.append(event)


        #################################
        ## event friend invitation     ##
        #################################

        memberEvents = member.getSession('event', None)
        if memberEvents:
            event = vo.Event()
            event['event'] = vo.Event.EVENT.MAIN__FRIEND_INVITATION_ACCEPTED
            event['data'] = memberEvents[0]
            event['sender'] = vo.Event.SENDER.SERVER
            event['receiver'] = vo.Event.RECEIVER.CLIENT_FB + str(member.facebook_id)
            event['transport'] = vo.Event.TRANSPORT.REQUEST
            event['timestamp'] = datetime.now()
            event['id'] = None

            eventList.append(event)

            member.delSession('event')


        #################################
        ## event open global chat      ##
        #################################

        openGlobalChatTime = time.strptime(ConfigKey.objects.filter(key='OPEN_GLOBAL_CHAT')[0].value, '%H:%M')
        closeGlobalChatTime = time.strptime(ConfigKey.objects.filter(key='CLOSE_GLOBAL_CHAT')[0].value, '%H:%M')
        currentTime = time.strptime(time.strftime( '%H:%M',time.localtime()), '%H:%M')

        print openGlobalChatTime
        print closeGlobalChatTime
        print currentTime

        if currentTime > openGlobalChatTime and currentTime < closeGlobalChatTime:
            event = vo.Event()
            event['event'] = vo.Event.EVENT.MAIN__OPEN_GLOBAL_CHAT
            event['data'] = {}
            event['sender'] = vo.Event.SENDER.SERVER
            event['receiver'] = vo.Event.RECEIVER.CLIENT_FB + str(member.facebook_id)
            event['transport'] = vo.Event.TRANSPORT.REQUEST
            event['timestamp'] = datetime.now()
            event['id'] = None

            eventList.append(event)


        return eventList

