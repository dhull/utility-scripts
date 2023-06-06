#! /usr/bin/perl

# From Bryant, for 0.12 to 1.4.6 direct terraform upgrade:
# AWS_PROFILE=qa terraform146 state replace-provider registry.terraform.io/-/archive registry.terraform.io/hashicorp/archive
# AWS_PROFILE=qa terraform146 state replace-provider registry.terraform.io/-/aws registry.terraform.io/hashicorp/aws

use autodie;
use strict;
use warnings;

use File::Slurp;
use Getopt::Long;
use Pod::Usage;
use YAML::XS;

# use JSON::XS;

my $context;

GetOptions(
  'context=s' => \$context,
) or pod2usage(-exitval => 2, -output => \*STDERR);

if (! -f "main.tf") {
  print STDERR "not a terraform directory\n";
  exit(1);
}

if (! $context) {
  $context = get_context_from_branch();
}

if (-x '/usr/local/bin/figlet') {
  # Figlet is a program for writing banners to the terminal.
  system('figlet', '-k', $context);
} else {
  print "\n${uc($context)}\n";
}

$ENV{AWS_PROFILE} = "fbot-$context";
$ENV{AWS_DEFAULT_REGION} = "us-east-1";
$ENV{FBT_AWS_ACCOUNT_ID} = ({
  sandbox       => '627208980326',
  qa            => '755386480951',
  staging       => '913709512847',
  production    => '644084073510',
})->{$context};

my $circleci_file = find_first(
  sub { -f $_[0] },
  [ '.circleci/config.yml', '../.circleci/config.yml' ]
);
print STDERR "found config $circleci_file\n";
my $circleci_yaml = File::Slurp::read_file($circleci_file);
my $circleci_config = YAML::XS::Load($circleci_yaml) or die;

# print JSON::XS::encode_json($circleci_config);
# print JSON::XS::encode_json($circleci_config->{jobs}->{deploy}->{steps}), "\n\n";

my $tf_action = shift(@ARGV);
my $tf_program = terraform_program();

my $tf_cmd = find_command(
  $circleci_config,
  $tf_action eq 'init'
    ? qr/^terraform\s+init/
    : qr/^terraform\s+apply/);
print STDERR "tf_cmd: $tf_cmd\n";

# Hacky way to get shell to expand env vars, remove quotes.
$ENV{CONTEXT} = $context;
chomp($tf_cmd = `echo $tf_cmd`);

print STDERR "1: $tf_cmd\n";


my %remove_arg = (
  '-reconfigure' => 1,
  '-auto-approve' => 1,
);

my %add_args = (
  init => [ '-backend=true', '-force-copy', '-get=true' ],
);

my @tf_args = grep({ ! exists $remove_arg{$_} } split(m/\s+/, $tf_cmd));

# @tf_args = map(var_expand($_, CONTEXT => $context, CIRCLE_SHA1 => ''), @tf_args);
splice(@tf_args, 0, 2);

my @add_args = exists $add_args{$tf_action} ? @{$add_args{$tf_action}} : ();

if ($tf_action eq 'init') {
  system('rm', '-rf', '.terraform');
}

my @cmd = ($tf_program, $tf_action, @tf_args, @add_args, @ARGV);

print STDERR "2: ", join(' ', @cmd), "\n";
exec(@cmd);
# If we get here then the exec failed.
exit(1);

########################################################################

sub terraform_program {
  my $tfversion = '0.12.31';

  my %versions = (
    '0.12' => '0.12.31',
    '0.13' => '0.13.7',
    '1.2'  => '1.2.8',
    '1.4'  => '1.4.6',
  );

  open(my $fh, '<', 'versions.tf') or die "versions.tf not found\n";
  while (my $l = <$fh>) {
    $l =~ m/required_version\s*=[^\d]*(\d+\.\d+)/ and do {
      if (! exists $versions{$1}) {
        die "no matching terraform version for $1 found\n";
      }
      $tfversion = $versions{$1};
      last;
    };
  }
  close($fh);

  return "terraform-$tfversion";
}

sub get_context_from_branch {
  my $branch = `git rev-parse --abbrev-ref HEAD`;
  chomp($branch);

  my %context = (
    master      => 'production',
    sandbox     => 'sandbox',
    qa          => 'qa',
    staging     => 'staging',
  );

  if (! exists $context{$branch}) {
    die "unknown context for \"$branch\" branch\n";
  }

  return $context{$branch};
}

sub var_expand {
  my ($var, %repl) = @_;
  $var =~ s/\$(?:\{([^\}]+)\}|(\w+))/$repl{$1 || $2}/g;
  return $var;
}

sub hash_descend {
  my $hr = shift(@_);

  while (scalar(@_) > 0) {
    ref($hr) eq 'HASH' or return undef;
    my $key = shift(@_);
    defined $hr->{$key} or return undef;
    $hr = $hr->{$key};
  }

  return $hr;
}

sub find_first {
  my ($test, $list) = @_;
  foreach my $entry (@$list) {
    if ($test->($entry)) {
      return $entry;
    }
  }
  return undef;
}

# Look in the circleci config to find the arguments for the terraform command.
sub find_command {
  my ($config, $pattern) = @_;

 step:
  foreach my $step (
    @{$config->{jobs}->{deploy}->{steps}},
    @{$config->{aliases}}
  ) {
    ref($step) eq 'HASH' or next step;
    my $command = hash_descend($step, 'run', 'command');
    if ($command && $command =~ $pattern) {
      return $command;
    }
  }
  return undef;
}

__END__

=head1 NAME

tf - Wrapper around terraform for Friendbuy

=head1 SYNOPSIS

tf [-c CONTEXT] [terraform verb] -- [terraform options]

=head1 OPTIONS

=over 4

= item B<-c I<CONTEXT>>

Specify the environment in which to run the terraform command (C<sandbox>,
C<qa>, C<staging>, or C<production>).  By default, the environment is guessed
from the current git branch.

=back

