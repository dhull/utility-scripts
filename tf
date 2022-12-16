#! /bin/sh

if ! test -f main.tf; then
    echo "not a terraform directory" 1>&2; exit 1
fi

tfversion=0.12.31
required_version="$(perl -n -e 'm/required_version\s*=[^\d]*(\d[\.\d]+)/ and do { print $1; exit; }' versions.tf)"
case "$required_version" in
     0.12|0.12.*)       tfversion=0.12.31 ;;
     0.13|0.13.*)       tfversion=0.13.7 ;;
     1.2.8)             tfversion=1.2.8 ;;
     *)
         echo "unknown required_version value \"$required_version\"" 1>&2
         exit 1
         ;;
esac

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
         -t=*|--tfversion=*)
             tfversion="${i#*=}"
             shift
             ;;
         -t|--terraform-version)
             tfversion="$2"
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

TERRAFORM="terraform-$tfversion"
if test "$(type -t "$TERRAFORM")" != file; then
   echo "could not find $TERRAFORM" 1>&2; exit 1
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
if ! test -f "$fbotenv.tfvars"; then
    echo "unknown fbotenv \"$fbotenv\"" 1>&2
    exit 1
fi

export AWS_PROFILE="fbot-${fbotenv}"
export AWS_ACCOUNT_ID=$(aws configure get arn | perl -n -e 'm/iam::(\d+)/ and print $1')
if test -z "$AWS_ACCOUNT_ID"; then echo "AWS_ACCOUNT_ID not found" 1>&2; exit 1; fi
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

function runexec {
    echo "$@" 1>&2
    exec "$@"
}

command="$1"
shift
case "$command" in
     init)
         if test -f "${fbotenv}.tfvars"; then
             tfvars_files=("${fbotenv}.tfvars")
             if test -f common.tfvars; then tfvars_files+=common.tfvars; fi
             init_args=$(
                 perl -n \
                      -e 'BEGIN { %KEYS = map(($_ => 1), qw( bucket profile key region )) }' \
                      -e 'm/^([\S]*)\s*=\s*\"(.*)\"/ and $KEYS{$1} and push(@v, "-backend-config=$1=$2");' \
                      -e 'END { print join(" ", @v) }' \
                      "${tfvars_files[@]}"
                      )
             #init_args="-backend-config=${fbotenv}.tfvars -backend-config=common.tfvars"
         else
             pwd="$(pwd)"
             echo "$pwd"

             # Defaults for all services.
             service=$(perl -e '$ENV{PWD} =~ m,/(fbt-.*?)/, and print $1')
             bucket="fbot-${fbotenv}-state"
             key=terraform.$service.tfstate
             profile="profile=$AWS_PROFILE";

             # Overrides for specific services.
             case "$pwd" in
                  */fbt-infrastructure)
                      bucket="fbt-remote-state-infrastructure-$AWS_ACCOUNT_ID"
                      key=terraform.fbt-infrastructure.tfstate
                      ;;
                  */fbt-long-job/terraform)
                      bucket="fbt-remote-state-$AWS_ACCOUNT_ID"
                      key=terraform.fbt-long-job.tfstate
                      ;;
                  */fbt-proxy/terraform)
                      bucket="fbt-remote-state-$AWS_ACCOUNT_ID"
                      key=terraform.fbt-proxy.tfstate
                      ;;
                  */fbt-account/infrastructure)
                      profile=
                      ;;
                  */fbt-account/infrastructure)
                      ;;
                  *)
                      echo "unknown dir; maybe use apex?" 1>&2; exit 1 ;;
             esac
             #  -backend-config=key=$key -backend-config=region=us-east-1 $profile"
             init_args="-backend-config=bucket=$bucket"
         fi

         # terraform init -var-file=${AWS_PROFILE#fbot-}.tfvars "$@"
         run rm -rf ".terraform"
         runexec $TERRAFORM init $init_args \
                   -backend=true \
                   -force-copy \
                   -get=true "$@"
         ;;
     plan|apply|graph|destroy)
         var_args=
         if egrep image_sha variables.tf >/dev/null 2>&1; then
             var_args="-var image_sha="
         fi
         runexec $TERRAFORM $command $var_args -var-file=${AWS_PROFILE#fbot-}.tfvars "$@"
         ;;
     *)
         echo "unknown command \"$command\"" 1>&2; exit 1
         ;;
esac

# AWS_PROFILE= terraform import -var-file production.tfvars module.pub_lambda.aws_lambda_function.lamdbda fbt-account_api
# AWS_PROFILE= terraform import -var-file production.tfvars module.pub_lambda.aws_lambda_function.lamdbda_alias fbt-account_api

