import json
import boto3
import datetime
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth

# ---------- CONFIG ----------
REGION = 'us-east-1'
OS_HOST = 'search-photos-qlnu3xesdeagft464evu73sjiu.us-east-1.es.amazonaws.com'   
OS_INDEX = 'photos'
OS_MASTER_USER = 'master'
OS_MASTER_PASS = 'Master@12345'

s3_client = boto3.client('s3')
rek_client = boto3.client('rekognition')

def get_os_client():
    """Create OpenSearch client with basic auth."""
    client = OpenSearch(
        hosts=[{'host': OS_HOST, 'port': 443}],
        http_auth=(OS_MASTER_USER, OS_MASTER_PASS),
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
    )
    return client

def lambda_handler(event, context):
    print("EVENT:", json.dumps(event))

    for record in event['Records']:
        bucket = record['s3']['bucket']['name']
        object_key = record['s3']['object']['key']

        # Decode URL-encoded key (spaces → +, etc.)
        import urllib.parse
        object_key = urllib.parse.unquote_plus(object_key)

        print(f"Processing: s3://{bucket}/{object_key}")

        # 1. Detect labels using Rekognition
        rek_response = rek_client.detect_labels(
            Image={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': object_key
                }
            },
            MaxLabels=10,
            MinConfidence=70
        )
        rek_labels = [label['Name'].lower() for label in rek_response['Labels']]
        print(f"Rekognition labels: {rek_labels}")

        # 2. Get S3 metadata (custom labels)
        s3_metadata = s3_client.head_object(Bucket=bucket, Key=object_key)
        metadata = s3_metadata.get('Metadata', {})
        print(f"S3 Metadata: {metadata}")

        custom_labels_str = metadata.get('customlabels', '')
        # Note: S3 lowercases all metadata keys, so 'customLabels' → 'customlabels'
        custom_labels = []
        if custom_labels_str:
            custom_labels = [label.strip().lower() for label in custom_labels_str.split(',') if label.strip()]
        print(f"Custom labels: {custom_labels}")

        # 3. Combine all labels
        all_labels = rek_labels + custom_labels
        print(f"All labels: {all_labels}")

        # 4. Create JSON document
        timestamp = datetime.datetime.now().strftime('%Y-%m-%dT%H:%M:%S')
        document = {
            'objectKey': object_key,
            'bucket': bucket,
            'createdTimestamp': timestamp,
            'labels': all_labels
        }
        print(f"Document to index: {json.dumps(document)}")

        # 5. Index in OpenSearch
        os_client = get_os_client()
        response = os_client.index(
            index=OS_INDEX,
            body=document,
            refresh='true'
        )
        print(f"OpenSearch response: {response}")

    return {
        'statusCode': 200,
        'body': json.dumps('Photo indexed successfully')
    }