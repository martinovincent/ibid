'''
Home page views.
'''

import logging
import urllib2
import json
import bidding.client as client
from django.conf import settings
from django.contrib.flatpages.models import FlatPage
from django.core.urlresolvers import reverse
from django.db.models import Count
from django.http import HttpResponseRedirect, HttpResponse
from django.shortcuts import render_to_response, redirect
from django.template import RequestContext
from django.views.decorators.csrf import csrf_exempt
from django.views.generic.list import ListView

from bidding.models import Auction
from bidding.models import ConvertHistory
from bidding.models import Member
from bidding.models import BidPackage
from bidding.models import ConfigKey
from bidding.models import Google_profile

from django_facebook.middleware import FacebookCanvasMiddleWare
from django_facebook.connect import connect_user
from django_facebook.canvas import generate_oauth_url
from django_facebook.exceptions import MissingPermissionsError
from open_facebook.api import FacebookAuthorization
from social_auth.db.django_models import UserSocialAuth
from social_auth.backends.google import GoogleOAuth2
logger = logging.getLogger('django')


def render_response(req, *args, **kwargs):
    kwargs['context_instance'] = RequestContext(req)
    return render_to_response(*args, **kwargs)

def get_data(uid,access_token):
    url = settings.GOOGLE_API_URL+'/%s/?access_token=%s' %(uid,access_token)
    serialized_data = urllib2.urlopen(url).read()
    data = json.loads(serialized_data)
    return data 

def canvashome(request):
    redirectTo = request.session.get('redirect_to', False)
    if redirectTo:
        del request.session['redirect_to']
        return HttpResponseRedirect(str(redirectTo))
    member=None
    fb_url = settings.FACEBOOK_APP_URL#.format(appname=settings.FACEBOOK_APP_NAME)
    share_title = ConfigKey.get('SHARE_APP_TITLE', 'iBidGames')
    share_description = ConfigKey.get('SHARE_APP_DESC', 'iBidGames is the first true online Interactive Auction, is the only interactive auction game within Facebook framework that allows players to win real items')
    if not request.user.is_authenticated():
        
        if not request.GET.get('facebook_login', None) and not request.GET.get('code', None):
            return render_response(request, 'login.html')
        else:    
            if not request.GET.get('code', None):    
                return redirect(generate_oauth_url())
            access_token = FacebookAuthorization.convert_code(request.GET.get('code', None), fb_url)['access_token']
            #Here the user dont came from facebook. The  dj-middleware redirects to this poin without authentication
            data = {
                'authorization_url': fb_url,
                'app_url': fb_url,
                'site_url': settings.SITE_NAME,
                'share_title': share_title,
                'share_description': share_description,
            }
            _action, _user = connect_user(request, access_token)
            return render_response(request, 'fb_redirect.html', data)
    #else:
    #    social_auth_user = UserSocialAuth.objects.filter(provider='google-oauth2').filter(user_id=request.user.id)
    #    if social_auth_user.count() > 0:
    #        social_auth_user = social_auth_user[0]
    #        data = get_data(social_auth_user.uid,social_auth_user.extra_data['access_token'])
    #        google_profile = Google_profile.objects.filter(user_id=social_auth_user.user_id)
    #        if google_profile.count() ==0:
    #            google_profile = Google_profile.objects.create(
    #                user_id= social_auth_user.user_id,
    #                profile_url =  data['url'],
    #                profile_picture_url = data['image']['url'],
    #                displayName = data['displayName'],
    #                email = data['emails'][0]['value'],
    #                gender =data['gender']
    #            )
    #            member=Member.objects.get(id=social_auth_user.user_id)
    #            member.bids_left = 0
    #            member.tokens_left = 2000
    #            member.save()
    #            client.update_tokens(member)
    #        else:
    #            google_profile = google_profile[0]
    #            profile_picture_url = data['image']['url']
    #            google_profile.save()
    
    if not member:           
        member = Member.objects.get(id=request.user.id)    
    #give free tokens from promo
    freeExtraTokens = request.session.get('freeExtraTokens', 0)
    if freeExtraTokens and not member.getSession('freeExtraTokens', None):
        member.tokens_left += freeExtraTokens
        member.setSession('freeExtraTokens', 'used')
        member.save()
        del request.session['freeExtraTokens']

    display_popup = False
    if not member.getSession('revisited'):
        display_popup = True
        member.setSession('revisited', True)
    try:
        auction_type = request.GET['auction_type']
    except Exception:
        auction_type = 'token'
    response = render_response(request, 'bidding/mainpage.html',
                               {'FACEBOOK_APP_URL':settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME),
                                'SITE_NAME_WOUT_BACKSLASH': settings.SITE_NAME_WOUT_BACKSLASH,
                                'display_popup': display_popup,
                                'facebook_user_id': member.facebook_id,
                                'tosintro': FlatPage.objects.filter(title="tacintro")[0].content,
                                'member': member,
                                'auction_type': auction_type,
                                'app_url': fb_url,
                                'site_url': settings.SITE_NAME,
                                'share_title': share_title,
                                'share_description': share_description,
                                'inCanvas':False})
    return response

def canvasapp(request):
    print "settings.FACEBOOK_APP_URL"
    print settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME)
    return HttpResponseRedirect(str(settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME)))


def standalone(request):
    member = request.user

    display_popup = False
    if not request.session.get("revisited"):
        request.session["revisited"] = True
        display_popup = True

    if request.COOKIES.get('dont_show_welcome_%s' %
            request.user.facebook_id):
        display_popup = False


    from random import shuffle

    debuggify = '''
    <script type="text/javaScript" src="https://cdn.debuggify.net/js/a4f458fc1c74cf2b60f0909da8531164/debuggify.logger.http.js"></script>
    '''

    qbaka = '''
    <script type="text/javascript">
    (function(a,c){a.__qbaka_eh=a.onerror;a.__qbaka_reports=[];a.onerror=function(){a.__qbaka_reports.push(arguments);if(a.__qbaka_eh)try{a.__qbaka_eh.apply(a,arguments)}catch(b){}};a.onerror.qbaka=1;a.qbaka={report:function(){a.__qbaka_reports.push([arguments, new Error()]);},customParams:{},set:function(a,b){qbaka.customParams[a]=b},exec:function(a){try{a()}catch(b){qbaka.reportException(b)}},reportException:function(){}};var b=c.createElement("script"),e=c.getElementsByTagName("script")[0],d=function(){e.parentNode.insertBefore(b,e)};b.type="text/javascript";b.async=!0;b.src="//cdn.qbaka.net/reporting.js";"[object Opera]"==a.opera?c.addEventListener("DOMContentLoaded",d):d();qbaka.key="a72f5cc63c961ae53e177e4ca071beb5"})(window,document);qbaka.options={autoStacktrace:1,trackEvents:1};
    </script>
    '''

    errorception = '''
    <script>
        (function(_,e,rr,s){_errs=[s];var c=_.onerror;_.onerror=function(){var a=arguments;_errs.push(a);
        c&&c.apply(this,a)};var b=function(){var c=e.createElement(rr),b=e.getElementsByTagName(rr)[0];
        c.src="//beacon.errorception.com/"+s+".js";c.async=!0;b.parentNode.insertBefore(c,b)};
        _.addEventListener?_.addEventListener("load",b,!1):_.attachEvent("onload",b)})
        (window,document,"script","51f15fe26c7008af50000013");
    </script>
    '''

    exceptional = '''
    <script type="text/javascript" src="http://js.exceptional.io/exceptional.js"></script>
    <script type="text/javascript">
      Exceptional.setKey('15fee4c8997d080bd8fcf93391bdee181f6f8133');
    </script>
    '''

    js_error_tracker = [debuggify, qbaka, errorception, exceptional]
    shuffle(js_error_tracker)

    js_error_tracker = ''
    if not settings.DEBUG:
        js_error_tracker = js_error_tracker[0]

    fb_url = settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME)
    share_title = ConfigKey.get('SHARE_APP_TITLE', 'iBidGames')
    share_description = ConfigKey.get('SHARE_APP_DESC', 'iBidGames is the first true online Interactive Auction, is the only interactive auction game within Facebook framework that allows players to win real items')

    response = render_response(request, 'bidding/mainpage.html',
                               {'display_popup': display_popup,
                                'facebook_user_id': member.facebook_id,
                                'tosintro': FlatPage.objects.filter(title="tacintro")[0].content,
                                'member': member,
                                'js_error_tracker': js_error_tracker,
                                'app_url': fb_url,
                                'site_url': settings.SITE_NAME,
                                'share_title': share_title,
                                'share_description': share_description,
                                'inCanvas':False})

    return response


def winners(request, page):
    member = request.user
    auctions = (Auction.objects.filter(is_active=True, winner__isnull=False)
                               .annotate(current_price=Count('bid'))
                               .select_related('item', 'winner')
                               .order_by('-won_date'))
    for auction in auctions:
        if auction.winner:
            auction.winner_member = Member.objects.filter(id=auction.winner.id)[0]
    #return render_response(request, 'bidding/winners.html',{'auctions': auctions, 'current_page': page})
    return render_response(request, 'bidding/ibidgames_winners.html',
                           {    'FACEBOOK_APP_URL':settings.FACEBOOK_APP_URL.format(appname=settings.FACEBOOK_APP_NAME),
                                'display_popup': False,
                                'facebook_user_id': member.facebook_id,
                                'tosintro': FlatPage.objects.filter(title="tacintro")[0].content,
                                'member': member,
                                'inCanvas':False,
                                'auctions': auctions,
                                'current_page': page})


@csrf_exempt
def auction_won_list(request):
    #FIXME ugly
    extra_query = ('(select count(*) from bidding_auctioninvoice '
                   'where bidding_auctioninvoice.status = %s '
                   'and bidding_auctioninvoice.auction_id=bidding_auction.id)')
    auctions = (Auction.objects.filter(winner=request.user)
                               .select_related('item')
                               .extra(select={'paid': extra_query},
                                      select_params=('paid',)))
    return render_response(request, 'bidding/auction_won_list.html',
        {'auctions': auctions})


def promo(request):
    promoCode = request.GET.get('promoCode', None)
    if promoCode:
        request.session['freeExtraTokens'] = 2000
        return HttpResponseRedirect(reverse('bidding_anonym_home'))
    return render_response(request, 'bidding/promo.html')




def history(request):
    member = request.user
    return render_response(request, "bidding/history.html", {'history': member.bids_history()})


class CurrencyHistory(ListView):
    paginated_by = settings.PAGINATED_BY
    template_name = "bidding/history.html"

    def get_queryset(self):
        return ConvertHistory.objects.filter(member=self.request.user)


def winner_email_example(request):
    if not request.user.is_authenticated():
        return HttpResponseRedirect(reverse('bidding_anonym_home'))

    finished = Auction.objects.filter(is_active=True, status__in=(
        'waiting_payment', 'paid')
    ).order_by('-won_date')

    auction = finished[0]
    user = request.user

    response = render_response(request, 'bidding/mail_winner.html',
                               {'user' : user,
                                'auction' : auction,
                                'site': settings.SITE_NAME,
                                'images_site':settings.IMAGES_SITE})
    return response


def example_404(request):
    response = render_response(request, '404.html')
    return response


def example_500(request):
    response = render_response(request, '500.html')
    return response

