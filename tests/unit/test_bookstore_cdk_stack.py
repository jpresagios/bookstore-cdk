import aws_cdk as core
import aws_cdk.assertions as assertions

from bookstore_cdk.bookstore_cdk_stack import BookstoreCdkStack

# example tests. To run these tests, uncomment this file along with the example
# resource in bookstore_cdk/bookstore_cdk_stack.py
def test_sqs_queue_created():
    app = core.App()
    stack = BookstoreCdkStack(app, "bookstore-cdk")
    template = assertions.Template.from_stack(stack)

#     template.has_resource_properties("AWS::SQS::Queue", {
#         "VisibilityTimeout": 300
#     })
