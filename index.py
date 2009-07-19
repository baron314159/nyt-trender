
from google.appengine.ext import webapp
from google.appengine.ext.webapp import template
from google.appengine.ext.webapp.util import run_wsgi_app
from google.appengine.api import urlfetch
from pygooglechart import SimpleLineChart, GroupedVerticalBarChart, Axis
import os, urllib, datetime, calendar, simplejson

NYT_ARTICLE_API_KEY = 'REPLACE WITH YOUR ARTICLE API KEY'

NYT_ARTICLE_API_URL = 'http://api.nytimes.com/svc/search/v1/article'
DEFAULT_QUERY_1 = 'palin'
DEFAULT_QUERY_2 = 'biden'
DEFAULT_YEAR_1 = 2008
DEFAULT_YEAR_2 = 2008
CURRENT_YEAR = datetime.date.today().year
VALID_YEARS = range(1981, CURRENT_YEAR+1)

CHART_WIDTH = 600
CHART_HEIGHT = 500
LINE_COLOR_1 = '207000'
LINE_COLOR_2 = '0077A0'
LINE_THICKNESS = 6

class ExpandoGroupedVerticalBarChart(GroupedVerticalBarChart):
    """A GroupedVerticalBarChart where the bars are scaled to fit."""

    def get_url_bits(self, data_class=None):
        url_bits = GroupedVerticalBarChart.get_url_bits(self, data_class)
        url_bits.append('chbh=a')
        return url_bits

def article_api_request(params):
    """Requests article search data from the NYT Article Search API.

    See http://developer.nytimes.com/docs/article_search_api/ for details on 
    valid parameters and the format of the response.
    
    The api key set above is added to the request. The return value is the 
    decoded JSON from the api call.
    """
    params = params.copy()
    params['api-key'] = NYT_ARTICLE_API_KEY
    url = NYT_ARTICLE_API_URL + '?' + urllib.urlencode(params)
    return simplejson.loads(urlfetch.fetch(url).content)

def article_api_trend_request(query, year):
    """Performs an API request for the trend data used by this application."""
    return article_api_request({
        'query': '%s publication_year:[%d]' % (query, year),
        'fields': 'url,title,small_image_url',
        'facets': 'publication_month,page_facet,des_facet,per_facet',
        'format': 'json',
        'rank': 'closest',
    })

def extract_month_counts(api_result):
    """Extract the number of articles published in each month."""
    mon_data = [0] * 12
    if 'facets' in api_result and 'publication_month' in api_result['facets']:
        pub_mon_facet = api_result['facets']['publication_month']
        # produce a map of month numbers to the number of articles in that month.
        mon_cnt_map = dict([(int(p['term'], 10), p['count']) for p in pub_mon_facet]) 
        # extract the article counts for each month 1 to 12
        for mon_num in range(1, 13):
            if mon_num in mon_cnt_map: 
                mon_data[mon_num-1] = int(mon_cnt_map[mon_num])
    return mon_data

def extract_page_counts(api_result):
    """Extract the number of articles per printed page."""
    if 'facets' in api_result and 'page_facet' in api_result['facets']:
        page_facet = api_result['facets']['page_facet']
        return dict([(int(p['term'], 10), p['count']) for p in page_facet]) 
    else:
        return {}

def extract_sorted_list(api_result, facet_name):
    """Extract sorted facet data."""
    if 'facets' in api_result and facet_name in api_result['facets']:
        facet = api_result['facets'][facet_name]
        items = [(p['term'], p['count']) for p in facet] 
        items.sort(lambda a, b: -cmp(a[1], b[1]))
        return items
    else:
        return []

def generate_mon_chart(mon_counts_1, mon_counts_2):
    """Generates a line graph plotting articles per month.

    Returns the url to a Google Chart showing the article counts in 
    mon_counts_1 vs. those in mon_counts_2.
    """
    # Get the first three letters of the calendar month names
    x_axis = [name[:3] for name in calendar.month_name][1:]
    min_y = min(mon_counts_1 + mon_counts_2)
    max_y = max(mon_counts_1 + mon_counts_2)
    step_y = ((max_y - min_y + 1) / 14) + 1
    y_axis = range(min_y, max_y, step_y)

    chart = SimpleLineChart(CHART_WIDTH, CHART_HEIGHT, y_range=[min_y, max_y])
    chart.add_data(mon_counts_1)
    chart.add_data(mon_counts_2)
    chart.set_colours([LINE_COLOR_1, LINE_COLOR_2])
    chart.set_axis_labels(Axis.BOTTOM, x_axis)
    chart.set_axis_labels(Axis.LEFT, y_axis)
    chart.set_line_style(0, thickness=LINE_THICKNESS)
    chart.set_line_style(1, thickness=LINE_THICKNESS)

    return chart.get_url()

def generate_page_chart(page_counts_1, page_counts_2):
    """Generates a bar graph plotting articles per printed page.

    Returns the url to a Google Chart showing the article counts in
    page_counts_1 vs those in page_counts_2.
    """
    pages = list(set(page_counts_1.keys() + page_counts_2.keys()))
    pages.sort()

    counts_1 = [0] * len(pages)
    counts_2 = [0] * len(pages)

    for page_idx in range(0, len(pages)):
        if pages[page_idx] in page_counts_1:
            counts_1[page_idx] = page_counts_1[pages[page_idx]]
        if pages[page_idx] in page_counts_2:
            counts_2[page_idx] = page_counts_2[pages[page_idx]]

    min_y = min(counts_1 + counts_2)
    max_y = max(counts_1 + counts_2)
    step_y = ((max_y - min_y + 1) / 14) + 1
    y_axis = range(min_y, max_y, step_y)

    chart = ExpandoGroupedVerticalBarChart(CHART_WIDTH, CHART_HEIGHT, 
        y_range=(min_y, max_y))
    chart.set_colours([LINE_COLOR_1, LINE_COLOR_2])
    chart.set_axis_labels(Axis.BOTTOM, pages)
    chart.set_axis_labels(Axis.LEFT, y_axis)
    chart.add_data(counts_1)
    chart.add_data(counts_2)

    return chart.get_url()

def render_template(out, template_name, values={}):
    "Renders template_name using values and writes the result to out."""
    template_path = os.path.join(os.path.dirname(__file__), template_name)
    out.write(template.render(template_path, values))

class TrendPage(webapp.RequestHandler):

    def get(self):
        query_1 = self.request.get('query_1', default_value=DEFAULT_QUERY_1)
        query_2 = self.request.get('query_2', default_value=DEFAULT_QUERY_2)
        year_1 = int(self.request.get('year_1', default_value=DEFAULT_YEAR_1))
        year_2 = int(self.request.get('year_2', default_value=DEFAULT_YEAR_2))

        if year_1 not in VALID_YEARS:
            year_1 = DEFAULT_YEAR_1
        if year_2 not in VALID_YEARS:
            year_2 = DEFAULT_YEAR_2

        # Get the trend data from the article API
        api_result_1 = article_api_trend_request(query_1, year_1)
        api_result_2 = article_api_trend_request(query_2, year_2)

        # Extract the number of articles published in each month
        mon_counts_1 = extract_month_counts(api_result_1)
        mon_counts_2 = extract_month_counts(api_result_2)

        # Calculate the total number of articles for each query
        total_1 = sum(mon_counts_1)
        total_2 = sum(mon_counts_2)

        # Plot the number of articles published in each month
        mon_chart_url = generate_mon_chart(mon_counts_1, mon_counts_2)

        # Extract the number of articles per printed page
        page_counts_1 = extract_page_counts(api_result_1)
        page_counts_2 = extract_page_counts(api_result_2)

        # Plot the number of articles per printed page
        page_chart_url = generate_page_chart(page_counts_1, page_counts_2)

        # Extract the top people for each query
        people_1 = extract_sorted_list(api_result_1, 'per_facet')
        people_2 = extract_sorted_list(api_result_2, 'per_facet')

        # Extract the top terms for each query
        terms_1 = extract_sorted_list(api_result_1, 'des_facet')
        terms_2 = extract_sorted_list(api_result_2, 'des_facet')

        # Extract the closest matching articles for each query 
        articles_1 = api_result_1['results']
        articles_2 = api_result_2['results']

        render_template(self.response.out, 'index.html', {
            'years': VALID_YEARS,
            'query_1': query_1,
            'query_2': query_2,
            'year_1': year_1,
            'year_2': year_2,
            'total_1': total_1,
            'total_2': total_2,
            'mon_chart_url': mon_chart_url,
            'page_chart_url': page_chart_url,
            'people_1': people_1,
            'people_2': people_2,
            'terms_1': terms_1,
            'terms_2': terms_2,
            'articles_1': articles_1,
            'articles_2': articles_2,
        })

def main():
    application = webapp.WSGIApplication([('/', TrendPage)], debug=True)
    run_wsgi_app(application)

if __name__ == "__main__":
    main()
