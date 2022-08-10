#! /bin/sh

while [[ $# -gt 0 ]]; do
    case "$1" in
         -e=*|--environment=*)
             fbotenv="${i#*=}"
             shift
             ;;
         -e|--environment)
             fbotenv="$2"
             shift 2
             ;;
         --)
             break
             ;;
         -*)
             echo "unknown option $1" 1>2
             exit 1
             ;;
         *)
             break
             ;;
    esac
done

if ! test -f main.tf -o -f "$fbotenv/main.tf"; then
    echo "not a terraform directory" 1>&2; exit 1
fi

if test -z "$fbotenv"; then
    branch="$(git rev-parse --abbrev-ref HEAD)"
    case "$branch" in
         master)
             fbotenv=production ;;
         sandbox|qa|applause|staging)
             fbotenv="$branch" ;;
         *)
             echo "unknown branch \"$branch\". Please specify an --environment" 1>&2; exit 1 ;;
    esac
fi
if ! test -f "$fbotenv.tfvars" -o -f "$fbotenv/main.tf"; then
    echo "unknown fbotenv \"$fbotenv\"" 1>&2
    exit 1
fi

export AWS_PROFILE="fbot-${fbotenv}"
#export AWS_ACCOUNT_ID=$(perl -n -e 'm/^aws_account_id\s*=\s*(["\047])?(\d+)\1/ and print $2;' $fbotenv.tfvars)
export AWS_ACCOUNT_ID=$(aws configure get arn | perl -n -e 'm/iam::(\d+)/ and print $1')
if test -z "$AWS_ACCOUNT_ID"; then echo "AWS_ACCOUNT_ID not found" 1>&2; exit 1; fi
#export AWS_REGION=$(perl -n -e 'm/^AWS_REGION\s*=\s*(["\047])?([^\1*]+)\1/ and print $2;' $fbotenv.tfvars)
export AWS_REGION=$(aws configure get region)
if test -z "$AWS_REGION"; then echo "AWS_REGION not found" 1>&2; exit 1; fi

if type -p figlet >/dev/null; then
    # Figlet is a program for writing banners to the terminal.
    figlet -k "$fbotenv"
else
    echo "\n${fbotenv}\n" | tr a-z A-Z
fi

echo "AWS_PROFILE=$AWS_PROFILE"
echo "AWS_ACCOUNT_ID=$AWS_ACCOUNT_ID"
echo "AWS_REGION=$AWS_REGION"

function run {
    echo "$@" 1>&2
    "$@"
}

command="$1"
shift
case "$command" in
     init)
         case $(pwd) in
              */fbt-infrastructure)
                  bucket="bucket=fbt-remote-state-infrastructure-$AWS_ACCOUNT_ID"
                  key="key=terraform.fbt-infrastructure.tfstate"
                  ;;
              */fbt-long-job/terraform)
                  bucket="bucket=fbt-remote-state-$AWS_ACCOUNT_ID"
                  key="key=terraform.fbt-long-job.tfstate"
                  ;;
              */fbt-event/infrastructure)
                  bucket="bucket=fbot-${fbotenv}-state"
                  key="key=terraform.fbt_event.tfstate"
                  ;;
              *)
                  echo "unknown dir; maybe use apex?" 1>&2; exit 1 ;;
         esac

         # terraform init -var-file=${AWS_PROFILE#fbot-}.tfvars "$@"
         run rm -rf ".terraform"
         run terraform init \
                   -backend-config="$bucket" \
                   -backend-config="$key" \
                   -backend-config="region=us-east-1" \
                   -backend-config="profile=$AWS_PROFILE" \
                   -backend=true \
                   -force-copy \
                   -get=true "$@"
         ;;
     plan|apply|graph)
         run terraform $command -var 'image_sha=' -var-file=${AWS_PROFILE#fbot-}.tfvars "$@"
         ;;
     *)
         echo "unknown command \"$command\"" 1>&2; exit 1
         ;;
esac
