"""
Model to store a microsite in the database.

The object is stored as a json representation of the python dict
that would have been used in the settings.

"""

import json

from django.db import models
from django.dispatch import receiver
from django.core.exceptions import ValidationError
from model_utils.models import TimeStampedModel

from simple_history.models import HistoricalRecords

from django.db.models.signals import pre_save, pre_delete
from django.db.models.base import ObjectDoesNotExist


def validate_json(values):
    """
    Guarantees the value passed is a valid json
    """
    try:
        json.loads(values)
    except ValueError:
        raise ValidationError("The values field must be a valid json.")


class Microsite(models.Model):
    """
    This is where the information about the microsite gets stored to the db.
    To achieve the maximum flexibility, most of the fields are stored inside
    a json field.

    Notes:
        - The key field was required for the dict definition at the settings, and it
        is used in some of the microsite_configuration methods.
        - The subdomain is outside of the json so that it is posible to use a db query
        to improve performance.
        - The values field must be validated on save to prevent the platform from crashing
        badly in the case the string is not able to be loaded as json.
    """
    key = models.CharField(max_length=63, db_index=True, unique=True)
    subdomain = models.CharField(max_length=127, db_index=True, unique=True)
    values = models.TextField(null=False, blank=True, validators=[validate_json])

    def __unicode__(self):
        return self.key

    def get_orgs(self):
        """
        Helper method to return a list of ORGs associated with our particular Microsite
        """
        return MicrositeOrgMapping.get_orgs_for_microsite_by_pk(self.id)

    @classmethod
    def get_microsite_for_domain(cls, domain):
        """
        Returns the microsite associated with this domain. Note that we always convert to lowercase, or
        None if no match
        """

        # remove any port number from the hostname
        domain = domain.split(':')[0]
        microsites = cls.objects.filter(subdomain__iexact=domain)

        return microsites[0] if microsites else None


class MicrositeHistory(TimeStampedModel):
    """
    This is an archive table for Microsites model, so that we can maintain a history of changes. Note that the
    key field is no longer unique
    """
    key = models.CharField(max_length=63, db_index=True)
    subdomain = models.CharField(max_length=127, db_index=True)
    values = models.TextField(null=False, blank=True, validators=[validate_json])

    def __unicode__(self):
        return self.key

    class Meta:
        """ Meta class for this Django model """
        verbose_name_plural = "Microsite histories"


def _make_archive_copy(instance):
    """
    Helper method to make a copy of a Microsite into the history table
    """
    archive_object = MicrositeHistory(
        key=instance.key,
        subdomain=instance.subdomain,
        values=instance.values,
    )
    archive_object.save()


@receiver(pre_delete, sender=Microsite)
def on_microsite_deleted(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """
    Archive the exam attempt when the item is about to be deleted
    Make a clone and populate in the History table
    """
    _make_archive_copy(instance)


@receiver(pre_save, sender=Microsite)
def on_microsite_updated(sender, instance, **kwargs):  # pylint: disable=unused-argument
    """
    Archive the microsite on an update operation
    """

    if instance.id:
        # on an update case, get the original and archive it
        original = Microsite.objects.get(id=instance.id)
        _make_archive_copy(original)


class MicrositeOrgMapping(models.Model):
    """
    Mapping of ORG to which Microsite it belongs
    """

    org = models.CharField(max_length=63, db_index=True, unique=True)
    microsite = models.ForeignKey(Microsite, db_index=True)

    # for archiving
    history = HistoricalRecords()

    @classmethod
    def get_orgs_for_microsite(cls, microsite_key):
        """
        Returns a list of ORGs associated with the microsite key, returned as a set
        """
        return cls.objects.filter(microsite__key=microsite_key).values_list('org', flat=True)

    @classmethod
    def get_orgs_for_microsite_by_pk(cls, microsite_pk):
        """
        Returns a list of ORGs associated with the microsite key, returned as a set
        """
        return cls.objects.filter(microsite_id=microsite_pk).values_list('org', flat=True)

    @classmethod
    def get_microsite_for_org(cls, org):
        """
        Returns the microsite object for a given ORG based on the table mapping, None if
        no mapping exists
        """

        try:
            item = cls.objects.get(org=org).select_related()
            return item.microsite
        except ObjectDoesNotExist:
            return None