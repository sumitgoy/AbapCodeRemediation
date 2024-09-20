import os
import boto3

# Create S3 and Bedrock clients
s3 = boto3.client('s3')
boto3_session = boto3.session.Session()
region = boto3_session.region_name

bedrock_agent_runtime_client = boto3.client('bedrock-agent-runtime')

# Get knowledge base id from environment variable
kb_id = os.environ.get("KNOWLEDGE_BASE_ID")

# Declare model id for calling RetrieveAndGenerate API
model_id = "anthropic.claude-3-5-sonnet-20240620-v1:0"
model_arn = f'arn:aws:bedrock:{region}::foundation-model/{model_id}'

# Add a prompt that will be suffixed to the extracted PDF content
def retrieveAndGenerate(input_text, kbId, model_arn, sessionId):
    try:
        if sessionId != "":
            response = bedrock_agent_runtime_client.retrieve_and_generate(
                input={
                'text': input_text
                },
                retrieveAndGenerateConfiguration={
                    'type': 'KNOWLEDGE_BASE',
                    'knowledgeBaseConfiguration': {
                        'generationConfiguration': {
                            'inferenceConfig': {
                                'textInferenceConfig': {
                                    'maxTokens': 4096,
                                    'temperature': 0.1,
                                    'topP': 1
                                }
                            },
            
                        },
                        'knowledgeBaseId': kbId,
                        'modelArn': model_arn
                    }
                },
                sessionId=sessionId
            )
        else:
            response = bedrock_agent_runtime_client.retrieve_and_generate(
                   input= { 
                       'text': input_text
                   },
                   retrieveAndGenerateConfiguration={
                       'type': 'KNOWLEDGE_BASE',
                      'externalSourcesConfiguration': { 
                         'generationConfiguration': { 
                            'inferenceConfig': { 
                               'textInferenceConfig': { 
                                  'maxTokens': 4096,
                                  'temperature': 0.1,
                                  'topP': 1
                               }
                            }
                         },
                         'modelArn': model_arn,
                         'sources': [ 
                            { 
                               's3Location': { 
                                  'uri': "s3://abapsourcecodeanalysis/report-3.rtf"
                               },
                               'sourceType': 'S3'
                            }
                         ]
                      },
                      'knowledgeBaseConfiguration': { 
                         'knowledgeBaseId': kbId,
                         'modelArn': model_arn,
                         'retrievalConfiguration': { 
                            'vectorSearchConfiguration': { 
                               'numberOfResults': 1,
                               'overrideSearchType': 'SEMANTIC'
                            }
                         }
                      }
                   }
            )


        return response
    except Exception as e:
        raise

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

def lambda_handler(event, context):
    bucket_name = 'abapsourcecodeanalysis'
    sessionId = ""
    
    # Step 1: Retrieve the latest file from S3
    latest_file_key = get_latest_file(bucket_name)
    if not latest_file_key:
        return {'statusCode': 500, 'body': 'No files found in S3 bucket.'}
    
    # Step 2: Get the content of the latest file
    file_content = get_file_content(bucket_name, latest_file_key)
    
    # Step 3: Include the file content in the prompt
    prompt = f"""
    Please analyze the following ABAP code and identify any deprecated or changed elements based on the latest 
    SAP S/4HANA Simplification List of 2023. Ensure the output of the program remains unchanged. 
    Provide the results in JSON object with the following fields for each correction: 
    Priority, Line Number, Correction Title, Correction Message, Suggestion Accuracy (percentage), Summary. 
    The response should contain only the JSON object.
    
    <question>
    ABAP Code:
    {file_content}
    </question>
    
    Assistant:"""
    
    #  Step 4: Call Bedrock with the entire file content (including the custom prompt and extracted content)
    response = retrieveAndGenerate(prompt, kb_id, model_arn, sessionId)
    generated_text = response['output']['text']
    print(generated_text)
    
    return generated_text
