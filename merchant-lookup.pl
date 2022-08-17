#! /usr/bin/perl

use strict;
use warnings;

# use Data::Dump;

use Getopt::Long;
use JSON::XS qw( decode_json encode_json );
use LWP::UserAgent;
use Pod::Usage;
use URI;

my $merchantId;
my $merchantName;
my $merchantUrl;
my $index;
my $environment = "production";
my @field;

my $json = JSON::XS->new->pretty(1)->canonical(1);

GetOptions(
  'id=s'                => \$merchantId,
  'name=s'              => \$merchantName,
  'url=s'               => \$merchantUrl,
  'index|i=i'           => \$index,
  'environment=s'       => \$environment,
  'field|f=s'           => sub { @field = split(m/,/, $_[1]) },
  'help'                => sub { pod2usage(0); }
) or die("bad command-line option");

if (! defined $merchantId && ! defined $merchantName && ! defined $merchantUrl) {
  pod2usage("Must specify --id, --name, or --url");
}

my $kinesis_host = kinesis_host($environment);

my $query = {
  query => {
    bool => {
      should => [
        ($merchantId ? { term => {"id.keyword" => $merchantId} } : ()),
        ($merchantName
         ? ({ match => { name => { query => $merchantName } } },
            { wildcard => { name => { value => "*${merchantName}*" } } })
         : ()),
        ($merchantUrl
         ? { wildcard => { "url" => { "value" => "*${merchantUrl}*" } } }
         : ()),
      ],
      minimum_should_match => 1,
    }
  }
};

my $data = es_request(
  method => 'GET',
  path => '/account_merchant/_search',
  body => $query,
);

my @hit = @{$data->{hits}->{hits}};

if (defined $index) {
  if ($index > scalar(@hit)) {
    die(sprintf("index > number of hits (%s > %s)\n", $index, scalar(@hit)));
  }
  @hit = ($hit[$index]);
}

if (scalar(@field) > 0) {
  if (scalar(@hit) > 1) {
    die("multiple hits:\n" .
        join('', map { "  $_: $hit[$_]->{_source}->{name} (score: $hit[$_]->{_score})\n" } (0..$#hit)));
  }
  print map("$hit[0]->{_source}->{$_}\n", @field);
} else {
  my $index = 0;
  foreach my $hit (@hit) {
    print "$index (score: $hit->{_score}): ", $json->encode($hit->{_source}), "\n";
    $index++;
  }
}

exit(0);

########################################################################

sub kinesis_host {
  my ($environment) = @_;

  return $environment eq 'production'
    ? 'kibana.fbot.me'
    : "kibana.fbot-${environment}.me";
}

my $ua;

BEGIN {
  $ENV{PERL_LWP_SSL_VERIFY_HOSTNAME} = 0;
  $ua = LWP::UserAgent->new();
}

sub es_request {
  my %arg = @_;

# POST https://kibana.fbot.me/_plugin/kibana/api/console/proxy?path=/account_merchant/_search&method=GET
# {
#   "query": {
#     "term": {
#       "id.keyword": "36da216e-9add-4468-b024-af1a6cd70c74"
#     }
#   }
# }

  my $uri = URI->new("https://${kinesis_host}/_plugin/kibana/api/console/proxy");
  $uri->query_form(
    method => $arg{method},
    path => $arg{path},
  );

  my $r = $ua->post(
    $uri,
    'Content-Type' => 'application/json',
    'kbn-version' => '7.10.2',
    'kbn-xsrf' => 'kibana',
    Content => encode_json($arg{body}),
  );

  # print STDERR Data::Dump::pp($arg{body}), "\n";
  # Data::Dump::dd($r);

  return decode_json($r->decoded_content());
}

__END__

=head1 NAME

merchant-lookup - Look up merchant information in Elasticsearch

=head1 SYNOPSIS

merchant-lookup.pl --help

merchant-lookup.pl --id MERCHANT_ID [OPTIONS]

merchant-lookup.pl --name MERCHANT_NAME [OPTIONS]

merchant-lookup.pl --url MERCHANT_URL [OPTIONS]

=head1 OPTIONS

=over 4

=item B<--field|-f> [B<id>|B<name>]

Specify a field to output.  If not specified, outputs the entire merchant
record.

=item B<--index|-i> I<INDEX>

If there are multiple results, specify which one to output.  Default: output
all results.

=item B<--environment|-e> I<ENVIRONMENT>

Environment, such as C<production> or C<sandbox>.  Default: C<production>.

=back
