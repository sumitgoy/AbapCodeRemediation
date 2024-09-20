import boto3
from botocore.client import Config
import json
import os

session = boto3.session.Session()
region = session.region_name
bedrock_config = Config(connect_timeout=600, read_timeout=600, retries={'max_attempts': 0})
bedrock_client = boto3.client('bedrock-runtime', region_name = region)
bedrock_agent_client = boto3.client("bedrock-agent-runtime", config=bedrock_config, region_name = region)
s3 = boto3.client('s3')
print(region)

# Function to retrieve the latest file from S3
def get_latest_file(bucket_name):
    response = s3.list_objects_v2(Bucket=bucket_name, Prefix='')
    files = response.get('Contents', [])
    
    if not files:
        return None  # No files found
    
    # Find the latest file based on 'LastModified' timestamp
    latest_file = max(files, key=lambda x: x['LastModified'])
    return latest_file['Key']

# Function to retrieve the content of the file from S3
def get_file_content(bucket_name, file_key):
    response = s3.get_object(Bucket=bucket_name, Key=file_key)
    content = response['Body'].read().decode('utf-8')
    return content

def retrieve(query, kbId, numberOfResults=1):
    return bedrock_agent_client.retrieve(
        retrievalQuery= {
            'text': query
        },
        knowledgeBaseId=kbId,
        retrievalConfiguration= {
            'vectorSearchConfiguration': {
                'numberOfResults': numberOfResults,
                'overrideSearchType': "HYBRID", # optional
            }
        }
    )

def get_contexts(retrievalResults):
    contexts = []
    for retrievedResult in retrievalResults: 
        contexts.append(retrievedResult['content']['text'])
    return contexts

def lambda_handler(event, context):
    bucket_name = event['Records'][0]['s3']['bucket']['name']
    kb_id = os.environ.get("KNOWLEDGE_BASE_ID")
    query = event["question"]
    sessionId = event["sessionId"]
    
    # Step 1: Retrieve the latest file from S3
    latest_file_key = get_latest_file(bucket_name)
    if not latest_file_key:
        return {'statusCode': 500, 'body': 'No files found in S3 bucket.'}
    
    # Step 2: Get the content of the latest file
    file_content = get_file_content(bucket_name, latest_file_key)

    
    
    responseR = retrieve(query, kb_id, 1)
    retrievalResults = responseR['retrievalResults']
    contexts = get_contexts(retrievalResults)
    print(contexts)

    # Step 3: Include the file content in the prompt
    prompt = f"""
    Please analyze the following ABAP code and identify any deprecated or changed elements based on the latest SAP S/4HANA Simplification List of 2023. Ensure the output of the program remains unchanged.Provide the results in JSON object with 
    following fields: priority, suggestion_accuracy (percentage), modified_code.The response should contain only the JSON object and no additional text and full code in modified_code. ABAP Code:
    
    Only return the JSON object.
    
    <context>
    {contexts}
    <context>


    <question>
    ABAP Code:
    {file_content}
    </question>
    
    Assistant:"""
    
    
    messages = [{"role": 'user', "content": prompt}]
    
    sonnet_payload = json.dumps({
        "anthropic_version": "bedrock-2023-05-31",
        "max_tokens": 4096,
        "messages": messages,
        "temperature": 0.1,
        "top_p": 0.5
    })
    
    modelId = 'anthropic.claude-3-5-sonnet-20240620-v1:0'  # change this to use a different version if needed
    accept = 'application/json'
    contentType = 'application/json'
    
    # Invoke Bedrock model
    response = bedrock_client.invoke_model(
        body=sonnet_payload, 
        modelId=modelId, 
        accept=accept, 
        contentType=contentType
    )
    
    response_body = json.loads(response.get('body').read())
    response_text = response_body.get('content')[0]['text']

    print(response_text)
    
    return {
        'statusCode': 200,
        'body': response_text
    }
