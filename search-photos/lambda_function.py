# update for demo of codepipeline

import json
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection

# ---------- CONFIG ----------
REGION = 'us-east-1'
OS_HOST = 'search-photos-qlnu3xesdeagft464evu73sjiu.us-east-1.es.amazonaws.com'
OS_INDEX = 'photos'
OS_MASTER_USER = 'master'
OS_MASTER_PASS = 'Master@12345'

LEX_BOT_ID = 'VEXQJDP8LO'
LEX_BOT_ALIAS_ID = 'TSTALIASID'   
LEX_LOCALE_ID = 'en_US'

lex_client = boto3.client('lexv2-runtime', region_name=REGION)

def get_os_client():
    client = OpenSearch(
        hosts=[{'host': OS_HOST, 'port': 443}],
        http_auth=(OS_MASTER_USER, OS_MASTER_PASS),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
    return client

def get_keywords_from_lex(query):
    """Send query to Lex and extract slot values (keywords)."""
    response = lex_client.recognize_text(
        botId=LEX_BOT_ID,
        botAliasId=LEX_BOT_ALIAS_ID,
        localeId=LEX_LOCALE_ID,
        sessionId='search-session',
        text=query
    )
    print(f"Lex response: {json.dumps(response, default=str)}")

    keywords = []

    # Extract slot values from the interpretation
    interpretations = response.get('interpretations', [])
    for interpretation in interpretations:
        intent = interpretation.get('intent', {})
        if intent.get('name') == 'SearchIntent':
            slots = intent.get('slots', {})
            for slot_name, slot_data in slots.items():
                if slot_data and slot_data.get('value'):
                    resolved = slot_data['value'].get('interpretedValue')
                    if resolved:
                        keywords.append(resolved.lower())
            break

    print(f"Extracted keywords: {keywords}")
    return keywords

def search_opensearch(keywords):
    """Query OpenSearch for photos matching any of the keywords."""
    os_client = get_os_client()

    if not keywords:
        return []

    # Build a bool query: the photo must match ALL keywords
    # Each keyword is searched in the "labels" field
    must_clauses = []
    for kw in keywords:
        must_clauses.append({
            'match': {
                'labels': kw
            }
        })

    query = {
        'size': 50,
        'query': {
            'bool': {
                'must': must_clauses
            }
        }
    }
    print(f"OpenSearch query: {json.dumps(query)}")

    response = os_client.search(index=OS_INDEX, body=query)
    print(f"OpenSearch response: {json.dumps(response, default=str)}")

    results = []
    for hit in response['hits']['hits']:
        source = hit['_source']
        photo_url = f"https://{source['bucket']}.s3.amazonaws.com/{source['objectKey']}"
        results.append({
            'url': photo_url,
            'labels': source['labels']
        })

    return results

def lambda_handler(event, context):
    print(f"EVENT: {json.dumps(event)}")

    # Get query from query string parameters
    query = None
    if event.get('queryStringParameters'):
        query = event['queryStringParameters'].get('q')

    if not query:
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'GET,OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
            },
            'body': json.dumps({'results': []})
        }

    print(f"Search query: {query}")

    # 1. Disambiguate query with Lex
    keywords = get_keywords_from_lex(query)

    # 2. Search OpenSearch
    if keywords:
        results = search_opensearch(keywords)
    else:
        results = []

    # 3. Return results
    return {
        'statusCode': 200,
        'headers': {
            'Access-Control-Allow-Origin': '*',
            'Access-Control-Allow-Methods': 'GET,OPTIONS',
            'Access-Control-Allow-Headers': 'Content-Type,X-Api-Key',
        },
        'body': json.dumps({'results': results})
    }